"""SQL for each aggregate. Services hold the business rules; this module only maps rows."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from mla.core.enums import (
    CatalogStatus, Condition, ItemStatus, JobStatus, ListingStatus, Marketplace,
)
from mla.core.models import (
    ExecutionLog, Job, JobItem, Listing, MarketplaceAccount, Product, ProductGroup,
    ProductImage, ProductMarketplaceData, ProductSummary, ProductVariant,
)
from mla.persistence.db import Database, now_iso

PRODUCT_FIELDS = (
    "internal_name", "title", "sku", "category", "subcategory", "brand", "model", "condition",
    "description", "features", "material", "package_contents", "warranty", "price_cents", "stock",
    "weight_g", "length_mm", "width_mm", "height_mm", "package_type", "availability_days",
    "shipping_notes", "status",
)


class DuplicateSkuError(ValueError):
    def __init__(self, sku: str):
        super().__init__(f"Já existe um produto ou variação com o SKU '{sku}'")
        self.sku = sku


def _product_values(p: Product) -> list[Any]:
    values = []
    for name in PRODUCT_FIELDS:
        value = getattr(p, name)
        values.append(value.value if hasattr(value, "value") else value)
    return values


# --------------------------------------------------------------------------- products
@dataclass
class ProductQuery:
    text: str = ""
    status: CatalogStatus | None = None
    group_id: int | None = None
    order_by: str = "updated_at"
    descending: bool = True
    limit: int | None = None


_ORDERABLE = {"updated_at", "internal_name", "title", "sku", "price_cents", "stock", "status", "created_at"}


class ProductRepository:
    def __init__(self, db: Database):
        self.db = db

    def insert(self, product: Product) -> int:
        now = now_iso()
        cols = ", ".join(PRODUCT_FIELDS)
        marks = ", ".join("?" for _ in PRODUCT_FIELDS)
        with self.db.transaction() as conn:
            try:
                cur = conn.execute(
                    f"INSERT INTO products ({cols}, created_at, updated_at) VALUES ({marks}, ?, ?)",
                    (*_product_values(product), now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise self._translate(exc, product) from exc
            product.id = cur.lastrowid
            product.created_at = product.updated_at = now
            self._save_children(conn, product)
        return product.id  # type: ignore[return-value]

    def update(self, product: Product) -> None:
        if product.id is None:
            raise ValueError("Produto sem id")
        now = now_iso()
        assignments = ", ".join(f"{name} = ?" for name in PRODUCT_FIELDS)
        with self.db.transaction() as conn:
            try:
                conn.execute(
                    f"UPDATE products SET {assignments}, updated_at = ? WHERE id = ?",
                    (*_product_values(product), now, product.id),
                )
            except sqlite3.IntegrityError as exc:
                raise self._translate(exc, product) from exc
            product.updated_at = now
            self._save_children(conn, product)

    def set_status(self, product_id: int, status: CatalogStatus) -> None:
        self.db.execute("UPDATE products SET status = ? WHERE id = ?", (status.value, product_id))

    def delete(self, product_ids: list[int]) -> int:
        if not product_ids:
            return 0
        marks = ",".join("?" for _ in product_ids)
        with self.db.transaction() as conn:
            return conn.execute(f"DELETE FROM products WHERE id IN ({marks})", product_ids).rowcount

    def sku_exists(self, sku: str, exclude_product_id: int | None = None) -> bool:
        row = self.db.query_one(
            "SELECT 1 FROM products WHERE sku = ? AND id IS NOT ? "
            "UNION SELECT 1 FROM product_variants WHERE sku = ? AND product_id IS NOT ?",
            (sku, exclude_product_id, sku, exclude_product_id),
        )
        return row is not None

    def id_for_sku(self, sku: str) -> int | None:
        return self.db.scalar("SELECT id FROM products WHERE sku = ?", (sku,))

    def get(self, product_id: int) -> Product | None:
        row = self.db.query_one("SELECT * FROM products WHERE id = ?", (product_id,))
        if row is None:
            return None
        product = self._row_to_product(row)
        product.images = [
            ProductImage(filename=r["filename"], position=r["position"], is_main=bool(r["is_main"]),
                         width=r["width"], height=r["height"], size_bytes=r["size_bytes"],
                         sha256=r["sha256"], id=r["id"], product_id=product_id)
            for r in self.db.query(
                "SELECT * FROM product_images WHERE product_id = ? ORDER BY position, id", (product_id,))
        ]
        product.variants = [
            ProductVariant(name=r["name"], attributes=json.loads(r["attributes_json"]), sku=r["sku"],
                           price_cents=r["price_cents"], stock=r["stock"], position=r["position"],
                           id=r["id"], product_id=product_id)
            for r in self.db.query(
                "SELECT * FROM product_variants WHERE product_id = ? ORDER BY position, id", (product_id,))
        ]
        for r in self.db.query("SELECT * FROM product_marketplace_data WHERE product_id = ?", (product_id,)):
            try:
                marketplace = Marketplace(r["marketplace"])
            except ValueError:
                continue
            product.marketplace_data[marketplace] = ProductMarketplaceData(
                marketplace=marketplace, enabled=bool(r["enabled"]), price_cents=r["price_cents"],
                category_id=r["category_id"], listing_type=r["listing_type"],
                attributes=json.loads(r["attributes_json"]), product_id=product_id,
            )
        return product

    def list_summaries(self, query: ProductQuery | None = None) -> list[ProductSummary]:
        q = query or ProductQuery()
        where, params = [], []
        if q.text:
            like = f"%{q.text.strip()}%"
            where.append("(p.internal_name LIKE ? OR p.title LIKE ? OR p.sku LIKE ? OR p.category LIKE ?"
                         " OR p.brand LIKE ?)")
            params += [like] * 5
        if q.status is not None:
            where.append("p.status = ?")
            params.append(CatalogStatus(q.status).value)  # Qt combos hand back plain str
        if q.group_id is not None:
            where.append("p.id IN (SELECT product_id FROM group_products WHERE group_id = ?)")
            params.append(q.group_id)
        order = q.order_by if q.order_by in _ORDERABLE else "updated_at"
        sql = (
            "SELECT p.id, p.internal_name, p.title, p.sku, p.category, p.price_cents, p.stock, p.status,"
            " p.updated_at,"
            " (SELECT COUNT(*) FROM product_images i WHERE i.product_id = p.id) AS image_count,"
            " (SELECT filename FROM product_images i WHERE i.product_id = p.id"
            "   ORDER BY i.is_main DESC, i.position LIMIT 1) AS main_image,"
            " (SELECT group_concat(marketplace) FROM product_marketplace_data d"
            "   WHERE d.product_id = p.id AND d.enabled = 1) AS marketplaces"
            " FROM products p"
            + (" WHERE " + " AND ".join(where) if where else "")
            + f" ORDER BY p.{order} COLLATE NOCASE {'DESC' if q.descending else 'ASC'}, p.id DESC"
            + (f" LIMIT {int(q.limit)}" if q.limit else "")
        )
        rows = self.db.query(sql, tuple(params))
        result = []
        for r in rows:
            mps = [Marketplace(m) for m in (r["marketplaces"] or "").split(",") if m in Marketplace._value2member_map_]
            result.append(ProductSummary(
                id=r["id"], internal_name=r["internal_name"], title=r["title"], sku=r["sku"],
                category=r["category"], price_cents=r["price_cents"], stock=r["stock"],
                status=CatalogStatus(r["status"]), image_count=r["image_count"],
                main_image=r["main_image"], updated_at=r["updated_at"], marketplaces=mps,
            ))
        return result

    def count_by_status(self) -> dict[CatalogStatus, int]:
        counts = {s: 0 for s in CatalogStatus}
        for r in self.db.query("SELECT status, COUNT(*) AS n FROM products GROUP BY status"):
            counts[CatalogStatus(r["status"])] = r["n"]
        return counts

    def all_ids(self) -> list[int]:
        return [r[0] for r in self.db.query("SELECT id FROM products ORDER BY id")]

    def image_files_in_use(self) -> set[str]:
        return {r[0] for r in self.db.query("SELECT DISTINCT filename FROM product_images")}

    # -- helpers
    @staticmethod
    def _translate(exc: sqlite3.IntegrityError, product: Product) -> Exception:
        message = str(exc)
        if "products.sku" in message:
            return DuplicateSkuError(product.sku)
        if "product_variants.sku" in message:
            skus = [v.sku for v in product.variants if v.sku]
            return DuplicateSkuError(", ".join(skus))
        return exc

    @staticmethod
    def _row_to_product(row: sqlite3.Row) -> Product:
        data = {name: row[name] for name in PRODUCT_FIELDS}
        data["condition"] = Condition(data["condition"])
        data["status"] = CatalogStatus(data["status"])
        return Product(**data, id=row["id"], created_at=row["created_at"], updated_at=row["updated_at"])

    def _save_children(self, conn: sqlite3.Connection, product: Product) -> None:
        pid = product.id
        now = now_iso()
        conn.execute("DELETE FROM product_images WHERE product_id = ?", (pid,))
        has_main = any(i.is_main for i in product.images)
        for pos, image in enumerate(product.images):
            image.position = pos
            if not has_main and pos == 0:
                image.is_main = True
            cur = conn.execute(
                "INSERT INTO product_images (product_id, filename, position, is_main, width, height,"
                " size_bytes, sha256, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (pid, image.filename, pos, int(image.is_main), image.width, image.height,
                 image.size_bytes, image.sha256, now),
            )
            image.id, image.product_id = cur.lastrowid, pid
        conn.execute("DELETE FROM product_variants WHERE product_id = ?", (pid,))
        for pos, variant in enumerate(product.variants):
            variant.position = pos
            try:
                cur = conn.execute(
                    "INSERT INTO product_variants (product_id, name, attributes_json, sku, price_cents,"
                    " stock, position) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (pid, variant.name, json.dumps(variant.attributes, ensure_ascii=False),
                     variant.sku or None, variant.price_cents, variant.stock, pos),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateSkuError(variant.sku or "") from exc
            variant.id, variant.product_id = cur.lastrowid, pid
        conn.execute("DELETE FROM product_marketplace_data WHERE product_id = ?", (pid,))
        for marketplace, data in product.marketplace_data.items():
            conn.execute(
                "INSERT INTO product_marketplace_data (product_id, marketplace, enabled, price_cents,"
                " category_id, listing_type, attributes_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (pid, marketplace.value, int(data.enabled), data.price_cents, data.category_id,
                 data.listing_type, json.dumps(data.attributes, ensure_ascii=False)),
            )
            data.product_id = pid


# --------------------------------------------------------------------------- groups
class GroupRepository:
    def __init__(self, db: Database):
        self.db = db

    def save(self, group: ProductGroup) -> int:
        now = now_iso()
        mps = json.dumps([m.value for m in group.marketplaces])
        with self.db.transaction() as conn:
            try:
                if group.id is None:
                    cur = conn.execute(
                        "INSERT INTO product_groups (name, description, marketplaces_json, created_at,"
                        " updated_at) VALUES (?, ?, ?, ?, ?)",
                        (group.name, group.description, mps, now, now))
                    group.id = cur.lastrowid
                    group.created_at = now
                else:
                    conn.execute(
                        "UPDATE product_groups SET name = ?, description = ?, marketplaces_json = ?,"
                        " updated_at = ? WHERE id = ?",
                        (group.name, group.description, mps, now, group.id))
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Já existe um grupo chamado '{group.name}'") from exc
            group.updated_at = now
            conn.execute("DELETE FROM group_products WHERE group_id = ?", (group.id,))
            group.product_ids = list(dict.fromkeys(group.product_ids))
            for pos, pid in enumerate(group.product_ids):
                conn.execute("INSERT INTO group_products (group_id, product_id, position) VALUES (?, ?, ?)",
                             (group.id, pid, pos))
        return group.id  # type: ignore[return-value]

    def get(self, group_id: int) -> ProductGroup | None:
        row = self.db.query_one("SELECT * FROM product_groups WHERE id = ?", (group_id,))
        return self._row_to_group(row) if row else None

    def list(self) -> list[ProductGroup]:
        return [self._row_to_group(r) for r in self.db.query("SELECT * FROM product_groups ORDER BY name COLLATE NOCASE")]

    def delete(self, group_id: int) -> None:
        self.db.execute("DELETE FROM product_groups WHERE id = ?", (group_id,))

    def groups_for_product(self, product_id: int) -> list[int]:
        return [r[0] for r in self.db.query("SELECT group_id FROM group_products WHERE product_id = ?", (product_id,))]

    def _row_to_group(self, row: sqlite3.Row) -> ProductGroup:
        ids = [r[0] for r in self.db.query(
            "SELECT product_id FROM group_products WHERE group_id = ? ORDER BY position", (row["id"],))]
        mps = [Marketplace(m) for m in json.loads(row["marketplaces_json"]) if m in Marketplace._value2member_map_]
        return ProductGroup(name=row["name"], description=row["description"], marketplaces=mps,
                            product_ids=ids, id=row["id"], created_at=row["created_at"],
                            updated_at=row["updated_at"])


# --------------------------------------------------------------------------- accounts
class AccountRepository:
    def __init__(self, db: Database):
        self.db = db

    def list(self, marketplace: Marketplace | None = None, active_only: bool = False) -> list[MarketplaceAccount]:
        sql, params = "SELECT * FROM marketplace_accounts WHERE 1=1", []
        if marketplace is not None:
            sql += " AND marketplace = ?"
            params.append(marketplace.value)
        if active_only:
            sql += " AND is_active = 1"
        rows = self.db.query(sql + " ORDER BY marketplace, id", tuple(params))
        return [self._row(r) for r in rows if r["marketplace"] in Marketplace._value2member_map_]

    def get(self, account_id: int) -> MarketplaceAccount | None:
        row = self.db.query_one("SELECT * FROM marketplace_accounts WHERE id = ?", (account_id,))
        return self._row(row) if row else None

    def default_for(self, marketplace: Marketplace) -> MarketplaceAccount | None:
        accounts = self.list(marketplace, active_only=True)
        return accounts[0] if accounts else None

    def save(self, account: MarketplaceAccount) -> int:
        with self.db.transaction() as conn:
            try:
                if account.id is None:
                    cur = conn.execute(
                        "INSERT INTO marketplace_accounts (marketplace, label, profile_dir, is_active, created_at)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (account.marketplace.value, account.label, account.profile_dir,
                         int(account.is_active), now_iso()))
                    account.id = cur.lastrowid
                else:
                    conn.execute(
                        "UPDATE marketplace_accounts SET label = ?, profile_dir = ?, is_active = ? WHERE id = ?",
                        (account.label, account.profile_dir, int(account.is_active), account.id))
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Já existe uma conta '{account.label}' neste marketplace") from exc
        return account.id  # type: ignore[return-value]

    @staticmethod
    def _row(r: sqlite3.Row) -> MarketplaceAccount:
        return MarketplaceAccount(marketplace=Marketplace(r["marketplace"]), label=r["label"],
                                  profile_dir=r["profile_dir"], is_active=bool(r["is_active"]),
                                  id=r["id"], created_at=r["created_at"])


# --------------------------------------------------------------------------- automation
_ITEM_SELECT = (
    "SELECT it.*, COALESCE(p.internal_name, it.product_name) AS display_name,"
    " COALESCE(p.sku, it.sku) AS display_sku, a.label AS account_label"
    " FROM automation_job_items it"
    " LEFT JOIN products p ON p.id = it.product_id"
    " LEFT JOIN marketplace_accounts a ON a.id = it.account_id"
)


class AutomationRepository:
    def __init__(self, db: Database):
        self.db = db

    # jobs
    def create_job(self, job: Job, items: list[JobItem]) -> int:
        now = now_iso()
        with self.db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO automation_jobs (label, kind, group_id, status, created_at) VALUES (?, ?, ?, ?, ?)",
                (job.label, job.kind, job.group_id, job.status.value, now))
            job.id, job.created_at = cur.lastrowid, now
            for pos, item in enumerate(items):
                item.job_id, item.position = job.id, pos
                cur = conn.execute(
                    "INSERT INTO automation_job_items (job_id, product_id, product_name, sku, marketplace,"
                    " account_id, position, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (job.id, item.product_id, item.product_name, item.sku, item.marketplace.value,
                     item.account_id, pos, item.status.value, now))
                item.id, item.created_at = cur.lastrowid, now
        return job.id  # type: ignore[return-value]

    def get_job(self, job_id: int) -> Job | None:
        row = self.db.query_one("SELECT * FROM automation_jobs WHERE id = ?", (job_id,))
        return self._job(row) if row else None

    def list_jobs(self, statuses: list[JobStatus] | None = None, limit: int = 200) -> list[Job]:
        sql, params = "SELECT * FROM automation_jobs", []
        if statuses:
            sql += f" WHERE status IN ({','.join('?' for _ in statuses)})"
            params = [s.value for s in statuses]
        sql += " ORDER BY id DESC LIMIT ?"
        return [self._job(r) for r in self.db.query(sql, (*params, limit))]

    def set_job_status(self, job_id: int, status: JobStatus) -> None:
        now = now_iso()
        if status is JobStatus.RUNNING:
            self.db.execute("UPDATE automation_jobs SET status = ?, started_at = COALESCE(started_at, ?)"
                            " WHERE id = ?", (status.value, now, job_id))
        elif status in (JobStatus.COMPLETED, JobStatus.CANCELLED):
            self.db.execute("UPDATE automation_jobs SET status = ?, finished_at = ? WHERE id = ?",
                            (status.value, now, job_id))
        else:
            self.db.execute("UPDATE automation_jobs SET status = ? WHERE id = ?", (status.value, job_id))

    # items
    def items_for_job(self, job_id: int) -> list[JobItem]:
        return [self._item(r) for r in self.db.query(_ITEM_SELECT + " WHERE it.job_id = ? ORDER BY it.position", (job_id,))]

    def get_item(self, item_id: int) -> JobItem | None:
        row = self.db.query_one(_ITEM_SELECT + " WHERE it.id = ?", (item_id,))
        return self._item(row) if row else None

    def next_queued_item(self) -> JobItem | None:
        row = self.db.query_one(
            _ITEM_SELECT + " JOIN automation_jobs j ON j.id = it.job_id"
            " WHERE it.status = 'queued' AND j.status IN ('pending', 'running')"
            " ORDER BY j.id, it.position LIMIT 1")
        return self._item(row) if row else None

    def update_item(self, item_id: int, **fields: Any) -> None:
        allowed = {"status", "step", "attempts", "error", "external_id", "url", "started_at", "finished_at"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Campos inválidos: {unknown}")
        values = [v.value if hasattr(v, "value") else v for v in fields.values()]
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(f"UPDATE automation_job_items SET {sets} WHERE id = ?", (*values, item_id))

    def active_item_for_target(self, product_id: int, marketplace: Marketplace, account_id: int) -> JobItem | None:
        row = self.db.query_one(
            _ITEM_SELECT + " WHERE it.product_id = ? AND it.marketplace = ? AND it.account_id = ?"
            " AND it.status IN ('queued', 'running', 'awaiting_review') LIMIT 1",
            (product_id, marketplace.value, account_id))
        return self._item(row) if row else None

    def items_with_status(self, statuses: list[ItemStatus]) -> list[JobItem]:
        marks = ",".join("?" for _ in statuses)
        return [self._item(r) for r in self.db.query(
            _ITEM_SELECT + f" WHERE it.status IN ({marks}) ORDER BY it.id", tuple(s.value for s in statuses))]

    def history(self, text: str = "", marketplace: Marketplace | None = None,
                status: ItemStatus | None = None, limit: int = 1000) -> list[JobItem]:
        where, params = ["it.status NOT IN ('queued')"], []
        if text:
            like = f"%{text}%"
            where.append("(display_name LIKE ? OR display_sku LIKE ? OR it.error LIKE ? OR it.external_id LIKE ?)")
            params += [like] * 4
        if marketplace:
            where.append("it.marketplace = ?")
            params.append(Marketplace(marketplace).value)  # Qt combos hand back plain str
        if status:
            where.append("it.status = ?")
            params.append(ItemStatus(status).value)
        sql = (f"SELECT * FROM ({_ITEM_SELECT}) it WHERE " + " AND ".join(where)
               + " ORDER BY COALESCE(it.finished_at, it.started_at, it.created_at) DESC, it.id DESC LIMIT ?")
        return [self._item(r) for r in self.db.query(sql, (*params, limit))]

    def count_items_by_status(self) -> dict[ItemStatus, int]:
        counts = {s: 0 for s in ItemStatus}
        for r in self.db.query("SELECT status, COUNT(*) AS n FROM automation_job_items GROUP BY status"):
            counts[ItemStatus(r["status"])] = r["n"]
        return counts

    # listings
    def upsert_listing(self, listing: Listing) -> None:
        now = now_iso()
        self.db.execute(
            "INSERT INTO listings (product_id, marketplace, account_id, status, external_id, url, published_at,"
            " last_item_id, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (product_id, marketplace, account_id) DO UPDATE SET status = excluded.status,"
            " external_id = CASE WHEN excluded.external_id <> '' THEN excluded.external_id ELSE listings.external_id END,"
            " url = CASE WHEN excluded.url <> '' THEN excluded.url ELSE listings.url END,"
            " published_at = COALESCE(excluded.published_at, listings.published_at),"
            " last_item_id = COALESCE(excluded.last_item_id, listings.last_item_id),"
            " updated_at = excluded.updated_at",
            (listing.product_id, listing.marketplace.value, listing.account_id, listing.status.value,
             listing.external_id, listing.url, listing.published_at, listing.last_item_id, now))

    def get_listing(self, product_id: int, marketplace: Marketplace, account_id: int) -> Listing | None:
        row = self.db.query_one(
            "SELECT * FROM listings WHERE product_id = ? AND marketplace = ? AND account_id = ?",
            (product_id, marketplace.value, account_id))
        return self._listing(row) if row else None

    def listings_for_product(self, product_id: int) -> list[Listing]:
        return [self._listing(r) for r in self.db.query(
            "SELECT * FROM listings WHERE product_id = ? ORDER BY marketplace, account_id", (product_id,))]

    def listing_counts(self) -> dict[tuple[Marketplace, ListingStatus], int]:
        result: dict[tuple[Marketplace, ListingStatus], int] = {}
        for r in self.db.query("SELECT marketplace, status, COUNT(*) AS n FROM listings GROUP BY marketplace, status"):
            if r["marketplace"] in Marketplace._value2member_map_:
                result[(Marketplace(r["marketplace"]), ListingStatus(r["status"]))] = r["n"]
        return result

    # logs
    def add_log(self, entry: ExecutionLog) -> int:
        now = now_iso()
        cur = self.db.execute(
            "INSERT INTO execution_logs (job_id, item_id, product_id, marketplace, level, step, message,"
            " details_json, screenshot, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entry.job_id, entry.item_id, entry.product_id, entry.marketplace, entry.level, entry.step,
             entry.message, json.dumps(entry.details, ensure_ascii=False, default=str), entry.screenshot, now))
        entry.id, entry.created_at = cur.lastrowid, now
        return entry.id  # type: ignore[return-value]

    def logs_for_item(self, item_id: int) -> list[ExecutionLog]:
        return [self._log(r) for r in self.db.query(
            "SELECT * FROM execution_logs WHERE item_id = ? ORDER BY id", (item_id,))]

    def recent_logs(self, limit: int = 20, levels: tuple[str, ...] = ()) -> list[ExecutionLog]:
        sql, params = "SELECT * FROM execution_logs", []
        if levels:
            sql += f" WHERE level IN ({','.join('?' for _ in levels)})"
            params = list(levels)
        return [self._log(r) for r in self.db.query(sql + " ORDER BY id DESC LIMIT ?", (*params, limit))]

    # row mappers
    @staticmethod
    def _job(r: sqlite3.Row) -> Job:
        return Job(label=r["label"], kind=r["kind"], group_id=r["group_id"], status=JobStatus(r["status"]),
                   id=r["id"], created_at=r["created_at"], started_at=r["started_at"], finished_at=r["finished_at"])

    @staticmethod
    def _item(r: sqlite3.Row) -> JobItem:
        return JobItem(
            job_id=r["job_id"], product_id=r["product_id"], marketplace=Marketplace(r["marketplace"]),
            account_id=r["account_id"], position=r["position"], status=ItemStatus(r["status"]),
            step=r["step"], attempts=r["attempts"], error=r["error"], external_id=r["external_id"],
            url=r["url"], id=r["id"], created_at=r["created_at"], started_at=r["started_at"],
            finished_at=r["finished_at"], product_name=r["display_name"] or "", sku=r["display_sku"] or "",
            account_label=r["account_label"] or "",
        )

    @staticmethod
    def _listing(r: sqlite3.Row) -> Listing:
        return Listing(product_id=r["product_id"], marketplace=Marketplace(r["marketplace"]),
                       account_id=r["account_id"], status=ListingStatus(r["status"]),
                       external_id=r["external_id"], url=r["url"], published_at=r["published_at"],
                       last_item_id=r["last_item_id"], id=r["id"], updated_at=r["updated_at"])

    @staticmethod
    def _log(r: sqlite3.Row) -> ExecutionLog:
        return ExecutionLog(level=r["level"], message=r["message"], step=r["step"], job_id=r["job_id"],
                            item_id=r["item_id"], product_id=r["product_id"], marketplace=r["marketplace"],
                            details=json.loads(r["details_json"]), screenshot=r["screenshot"], id=r["id"],
                            created_at=r["created_at"])


# --------------------------------------------------------------------------- settings
class SettingsRepository:
    def __init__(self, db: Database):
        self.db = db

    def get(self, key: str, default: Any = None) -> Any:
        row = self.db.query_one("SELECT value_json FROM application_settings WHERE key = ?", (key,))
        return json.loads(row[0]) if row else default

    def set(self, key: str, value: Any) -> None:
        self.db.execute(
            "INSERT INTO application_settings (key, value_json, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT (key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False), now_iso()))

    def all(self) -> dict[str, Any]:
        return {r["key"]: json.loads(r["value_json"]) for r in self.db.query("SELECT * FROM application_settings")}
