"""SQL for product compatibilities (product fits brand/model/version/years)."""
from __future__ import annotations

import sqlite3
from typing import Any

from mla.core.enums import DataSource, Verification
from mla.core.models import Compatibility
from mla.persistence.db import Database, now_iso

_FIELDS = ("product_id", "brand", "model", "version", "year_from", "year_to", "reference_code", "notes", "source",
           "source_detail", "verification")
_SELECT = ("SELECT c.*, p.internal_name AS product_name, p.sku AS product_sku FROM product_compatibilities c"
           " JOIN products p ON p.id = c.product_id")


class DuplicateCompatibilityError(ValueError):
    pass


class CompatibilityRepository:
    def __init__(self, db: Database):
        self.db = db

    def get(self, compat_id: int) -> Compatibility | None:
        row = self.db.query_one(_SELECT + " WHERE c.id = ?", (compat_id,))
        return _row(row) if row else None

    def list_for_product(self, product_id: int) -> list[Compatibility]:
        return [_row(r) for r in self.db.query(
            _SELECT + " WHERE c.product_id = ? ORDER BY c.brand COLLATE NOCASE, c.model COLLATE NOCASE,"
            " c.year_from, c.id", (product_id,))]

    @staticmethod
    def _where(text: str, verification: Verification | None, source: DataSource | None,
               product_id: int | None) -> tuple[str, list[Any]]:
        where, params = [], []
        if text.strip():
            like = f"%{text.strip()}%"
            where.append("(c.brand LIKE ? OR c.model LIKE ? OR c.version LIKE ? OR c.reference_code LIKE ?"
                         " OR p.sku LIKE ? OR p.internal_name LIKE ?)")
            params += [like] * 6
        if verification is not None:
            where.append("c.verification = ?")
            params.append(Verification(verification).value)
        if source is not None:
            where.append("c.source = ?")
            params.append(DataSource(source).value)
        if product_id is not None:
            where.append("c.product_id = ?")
            params.append(product_id)
        return (" WHERE " + " AND ".join(where) if where else ""), params

    def search(self, text: str = "", verification: Verification | None = None, source: DataSource | None = None,
               product_id: int | None = None, limit: int = 500, offset: int = 0) -> list[Compatibility]:
        where, params = self._where(text, verification, source, product_id)
        sql = (_SELECT + where + " ORDER BY c.brand COLLATE NOCASE, c.model COLLATE NOCASE, c.year_from, c.id"
               " LIMIT ? OFFSET ?")
        return [_row(r) for r in self.db.query(sql, (*params, int(limit), max(0, int(offset))))]

    def count(self, text: str = "", verification: Verification | None = None, source: DataSource | None = None,
              product_id: int | None = None) -> int:
        where, params = self._where(text, verification, source, product_id)
        return self.db.scalar("SELECT COUNT(*) FROM product_compatibilities c JOIN products p ON p.id = c.product_id"
                              + where, tuple(params)) or 0

    def find_duplicate(self, c: Compatibility) -> int | None:
        return self.db.scalar(
            "SELECT id FROM product_compatibilities WHERE product_id = ? AND brand = ? COLLATE NOCASE"
            " AND model = ? COLLATE NOCASE AND version = ? COLLATE NOCASE AND IFNULL(year_from, 0) = ?"
            " AND IFNULL(year_to, 0) = ? AND id IS NOT ?",
            (c.product_id, c.brand, c.model, c.version, c.year_from or 0, c.year_to or 0, c.id))

    def save(self, c: Compatibility) -> int:
        now = now_iso()
        values = [getattr(c, name).value if hasattr(getattr(c, name), "value") else getattr(c, name)
                  for name in _FIELDS]
        with self.db.transaction() as conn:
            try:
                if c.id is None:
                    cur = conn.execute(
                        f"INSERT INTO product_compatibilities ({', '.join(_FIELDS)}, created_at, updated_at)"
                        f" VALUES ({', '.join('?' for _ in _FIELDS)}, ?, ?)", (*values, now, now))
                    c.id, c.created_at = cur.lastrowid, now
                else:
                    conn.execute(
                        f"UPDATE product_compatibilities SET {', '.join(f'{n} = ?' for n in _FIELDS)},"
                        " updated_at = ? WHERE id = ?", (*values, now, c.id))
            except sqlite3.IntegrityError as exc:
                if "UNIQUE" in str(exc).upper():
                    raise DuplicateCompatibilityError("Essa compatibilidade já está cadastrada para o produto.") \
                        from exc
                raise
        c.updated_at = now
        return c.id  # type: ignore[return-value]

    def delete(self, ids: list[int]) -> int:
        if not ids:
            return 0
        marks = ",".join("?" for _ in ids)
        with self.db.transaction() as conn:
            return conn.execute(f"DELETE FROM product_compatibilities WHERE id IN ({marks})", ids).rowcount

    def set_verification(self, ids: list[int], verification: Verification) -> int:
        if not ids:
            return 0
        marks = ",".join("?" for _ in ids)
        with self.db.transaction() as conn:
            return conn.execute(
                f"UPDATE product_compatibilities SET verification = ?, updated_at = ? WHERE id IN ({marks})",
                (Verification(verification).value, now_iso(), *ids)).rowcount

    def confirmed_count(self, product_id: int) -> int:
        return self.db.scalar("SELECT COUNT(*) FROM product_compatibilities WHERE product_id = ?"
                              " AND verification = 'confirmed'", (product_id,)) or 0

    def counts_by_verification(self) -> dict[Verification, int]:
        counts = {v: 0 for v in Verification}
        for r in self.db.query("SELECT verification, COUNT(*) AS n FROM product_compatibilities GROUP BY verification"):
            counts[Verification(r["verification"])] = r["n"]
        return counts


def _row(r: sqlite3.Row) -> Compatibility:
    return Compatibility(
        product_id=r["product_id"], model=r["model"], brand=r["brand"], version=r["version"],
        year_from=r["year_from"], year_to=r["year_to"], reference_code=r["reference_code"], notes=r["notes"],
        source=DataSource(r["source"]), source_detail=r["source_detail"],
        verification=Verification(r["verification"]), id=r["id"], created_at=r["created_at"],
        updated_at=r["updated_at"], product_name=r["product_name"], sku=r["product_sku"])
