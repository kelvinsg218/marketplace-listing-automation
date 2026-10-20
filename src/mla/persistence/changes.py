"""Storage of the master catalog change history (migration 0008)."""
from __future__ import annotations

from dataclasses import dataclass

from mla.core.changes import FieldChange
from mla.persistence.db import Database, now_iso


@dataclass
class ChangeRecord:
    product_id: int | None
    sku: str
    field: str
    label: str
    old: str
    new: str
    source: str
    created_at: str
    id: int | None = None


class ChangeRepository:
    def __init__(self, db: Database):
        self.db = db

    def add(self, product_id: int, sku: str, changes: list[FieldChange], source: str) -> None:
        if not changes:
            return
        now = now_iso()
        with self.db.transaction() as conn:
            conn.executemany(
                "INSERT INTO product_changes (product_id, sku, field, label, old_value, new_value, source, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(product_id, sku, c.field, c.label, c.old, c.new, source, now) for c in changes])

    def for_product(self, product_id: int, limit: int = 500) -> list[ChangeRecord]:
        return [ChangeRecord(r["product_id"], r["sku"], r["field"], r["label"], r["old_value"], r["new_value"],
                             r["source"], r["created_at"], r["id"])
                for r in self.db.query("SELECT * FROM product_changes WHERE product_id = ? ORDER BY id DESC LIMIT ?",
                                       (product_id, limit))]

    def recent(self, limit: int = 1000) -> list[ChangeRecord]:
        return [ChangeRecord(r["product_id"], r["sku"], r["field"], r["label"], r["old_value"], r["new_value"],
                             r["source"], r["created_at"], r["id"])
                for r in self.db.query("SELECT * FROM product_changes ORDER BY id DESC LIMIT ?", (limit,))]
