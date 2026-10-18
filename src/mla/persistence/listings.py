"""SQL for prepared offers (the `listings` table): content overrides and preparation state.

The automation repository keeps writing the publication columns (status while queued/running,
external id, url, published_at); this repository owns the content columns.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from mla.core.enums import CatalogStatus, ListingStatus, Marketplace
from mla.core.models import Listing, ListingRow
from mla.persistence.db import Database, now_iso
from mla.persistence.repositories import listing_from_row

_ROW_SELECT = (
    "SELECT l.*, p.internal_name AS product_name, p.sku AS product_sku, p.status AS product_status,"
    " COALESCE(NULLIF(TRIM(l.title), ''), p.title) AS effective_title,"
    " COALESCE(l.price_cents, d.price_cents, p.price_cents) AS effective_price,"
    " a.label AS account_label,"
    " (SELECT filename FROM product_images i WHERE i.product_id = p.id"
    "   ORDER BY i.is_main DESC, i.position LIMIT 1) AS main_image"
    " FROM listings l"
    " JOIN products p ON p.id = l.product_id"
    " LEFT JOIN marketplace_accounts a ON a.id = l.account_id"
    " LEFT JOIN product_marketplace_data d ON d.product_id = l.product_id AND d.marketplace = l.marketplace"
)


class ListingExistsError(ValueError):
    pass


class ListingRepository:
    def __init__(self, db: Database):
        self.db = db

    def get(self, listing_id: int) -> Listing | None:
        row = self.db.query_one("SELECT * FROM listings WHERE id = ?", (listing_id,))
        return listing_from_row(row) if row else None

    def get_for(self, product_id: int, marketplace: Marketplace, account_id: int) -> Listing | None:
        row = self.db.query_one("SELECT * FROM listings WHERE product_id = ? AND marketplace = ? AND account_id = ?",
                                (product_id, Marketplace(marketplace).value, account_id))
        return listing_from_row(row) if row else None

    def for_product(self, product_id: int) -> list[Listing]:
        return [listing_from_row(r) for r in self.db.query(
            "SELECT * FROM listings WHERE product_id = ? ORDER BY marketplace, account_id", (product_id,))]

    def create(self, listing: Listing) -> int:
        now = now_iso()
        try:
            cur = self.db.execute(
                "INSERT INTO listings (product_id, marketplace, account_id, status, updated_at, created_at, title,"
                " description, price_cents, stock, category_id, listing_type, attributes_json, images_json, notes)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (listing.product_id, listing.marketplace.value, listing.account_id, listing.status.value, now, now,
                 listing.title, listing.description, listing.price_cents, listing.stock, listing.category_id,
                 listing.listing_type, json.dumps(listing.attributes, ensure_ascii=False),
                 json.dumps(listing.image_files), listing.notes))
        except sqlite3.IntegrityError as exc:
            raise ListingExistsError("Já existe um anúncio deste produto nesta conta.") from exc
        listing.id, listing.created_at, listing.updated_at = cur.lastrowid, now, now
        return listing.id  # type: ignore[return-value]

    def save_content(self, listing: Listing) -> None:
        now = now_iso()
        self.db.execute(
            "UPDATE listings SET status = ?, title = ?, description = ?, price_cents = ?, stock = ?, category_id = ?,"
            " listing_type = ?, attributes_json = ?, images_json = ?, notes = ?, approved_at = ?, approved_hash = ?,"
            " updated_at = ? WHERE id = ?",
            (listing.status.value, listing.title, listing.description, listing.price_cents, listing.stock,
             listing.category_id, listing.listing_type, json.dumps(listing.attributes, ensure_ascii=False),
             json.dumps(listing.image_files), listing.notes, listing.approved_at, listing.approved_hash, now,
             listing.id))
        listing.updated_at = now

    def set_status(self, listing_id: int, status: ListingStatus, approved_at: str | None = None,
                   approved_hash: str = "") -> None:
        self.db.execute("UPDATE listings SET status = ?, approved_at = ?, approved_hash = ?, updated_at = ?"
                        " WHERE id = ?", (status.value, approved_at, approved_hash, now_iso(), listing_id))

    def delete(self, ids: list[int]) -> int:
        if not ids:
            return 0
        marks = ",".join("?" for _ in ids)
        with self.db.transaction() as conn:
            return conn.execute(f"DELETE FROM listings WHERE id IN ({marks})", ids).rowcount

    @staticmethod
    def _where(marketplace: Marketplace | None, account_id: int | None, statuses: list[ListingStatus] | None,
               text: str) -> tuple[str, list[Any]]:
        where, params = [], []
        if marketplace is not None:
            where.append("l.marketplace = ?")
            params.append(Marketplace(marketplace).value)
        if account_id is not None:
            where.append("l.account_id = ?")
            params.append(account_id)
        if statuses:
            where.append(f"l.status IN ({','.join('?' for _ in statuses)})")
            params += [ListingStatus(s).value for s in statuses]
        if text.strip():
            like = f"%{text.strip()}%"
            where.append("(p.internal_name LIKE ? OR p.sku LIKE ? OR p.title LIKE ? OR l.title LIKE ?)")
            params += [like] * 4
        return (" WHERE " + " AND ".join(where) if where else ""), params

    def rows(self, marketplace: Marketplace | None = None, account_id: int | None = None,
             statuses: list[ListingStatus] | None = None, text: str = "", limit: int = 200,
             offset: int = 0) -> list[ListingRow]:
        where, params = self._where(marketplace, account_id, statuses, text)
        sql = _ROW_SELECT + where + " ORDER BY l.updated_at DESC, l.id DESC LIMIT ? OFFSET ?"
        result = []
        for r in self.db.query(sql, (*params, int(limit), max(0, int(offset)))):
            result.append(ListingRow(
                listing=listing_from_row(r), product_name=r["product_name"], sku=r["product_sku"],
                title=r["effective_title"] or "", price_cents=r["effective_price"],
                account_label=r["account_label"] or "", main_image=r["main_image"],
                product_status=CatalogStatus(r["product_status"])))
        return result

    def count(self, marketplace: Marketplace | None = None, account_id: int | None = None,
              statuses: list[ListingStatus] | None = None, text: str = "") -> int:
        where, params = self._where(marketplace, account_id, statuses, text)
        return self.db.scalar("SELECT COUNT(*) FROM listings l JOIN products p ON p.id = l.product_id" + where,
                              tuple(params)) or 0

    def counts_by_status(self, marketplace: Marketplace | None = None,
                         account_id: int | None = None) -> dict[ListingStatus, int]:
        where, params = self._where(marketplace, account_id, None, "")
        counts = {s: 0 for s in ListingStatus}
        for r in self.db.query("SELECT l.status, COUNT(*) AS n FROM listings l" + where + " GROUP BY l.status",
                               tuple(params)):
            counts[ListingStatus(r["status"])] = r["n"]
        return counts

    def ids_in_preparation(self, product_id: int) -> list[int]:
        return [r[0] for r in self.db.query(
            "SELECT id FROM listings WHERE product_id = ? AND status IN ('draft', 'incomplete', 'ready', 'approved')",
            (product_id,))]
