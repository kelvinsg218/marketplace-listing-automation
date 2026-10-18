"""SQL for import batches, their planned rows and saved mapping templates."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from mla.core.enums import ImportAction, ImportStatus
from mla.core.models import ImportBatch, ImportRow, ImportTemplate
from mla.persistence.db import Database, now_iso

_ROW_COLUMNS = ("batch_id", "row_no", "action", "decision", "sku", "name", "product_id", "parent_sku", "data_json",
                "changes_json", "issues_json", "media_json", "outcome")


class ImportRepository:
    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------------ batches
    def create_batch(self, batch: ImportBatch) -> int:
        now = now_iso()
        cur = self.db.execute(
            "INSERT INTO import_batches (source_name, source_path, source_sha256, format, target, status,"
            " mapping_json, options_json, counts_json, message, staging_dir, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (batch.source_name, batch.source_path, batch.source_sha256, batch.format, batch.target,
             batch.status.value, _dump(batch.mapping), _dump(batch.options), _dump(batch.counts), batch.message,
             batch.staging_dir, now))
        batch.id, batch.created_at = cur.lastrowid, now
        return batch.id  # type: ignore[return-value]

    def update_batch(self, batch_id: int, **fields: Any) -> None:
        allowed = {"status", "counts", "message", "planned_at", "finished_at", "staging_dir", "options"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Campos inválidos: {unknown}")
        sets, values = [], []
        for key, value in fields.items():
            column = {"counts": "counts_json", "options": "options_json"}.get(key, key)
            sets.append(f"{column} = ?")
            values.append(_dump(value) if key in ("counts", "options") else
                          (value.value if hasattr(value, "value") else value))
        self.db.execute(f"UPDATE import_batches SET {', '.join(sets)} WHERE id = ?", (*values, batch_id))

    def get_batch(self, batch_id: int) -> ImportBatch | None:
        row = self.db.query_one("SELECT * FROM import_batches WHERE id = ?", (batch_id,))
        return _batch(row) if row else None

    def list_batches(self, limit: int = 100) -> list[ImportBatch]:
        return [_batch(r) for r in self.db.query("SELECT * FROM import_batches ORDER BY id DESC LIMIT ?", (limit,))]

    def batches_with_status(self, statuses: list[ImportStatus]) -> list[ImportBatch]:
        marks = ",".join("?" for _ in statuses)
        return [_batch(r) for r in self.db.query(
            f"SELECT * FROM import_batches WHERE status IN ({marks}) ORDER BY id", tuple(s.value for s in statuses))]

    # ------------------------------------------------------------------ rows
    def add_rows(self, rows: list[ImportRow]) -> None:
        if not rows:
            return
        with self.db.transaction() as conn:
            conn.executemany(
                f"INSERT INTO import_rows ({', '.join(_ROW_COLUMNS)}) VALUES ({', '.join('?' for _ in _ROW_COLUMNS)})",
                [(r.batch_id, r.row_no, r.action.value, r.decision, r.sku, r.name, r.product_id, r.parent_sku,
                  _dump(r.data), _dump(r.changes), _dump(r.issues), _dump(r.media), r.outcome) for r in rows])

    def update_row(self, row: ImportRow) -> None:
        self.db.execute(
            "UPDATE import_rows SET action = ?, decision = ?, product_id = ?, data_json = ?, changes_json = ?,"
            " issues_json = ?, media_json = ?, outcome = ? WHERE id = ?",
            (row.action.value, row.decision, row.product_id, _dump(row.data), _dump(row.changes), _dump(row.issues),
             _dump(row.media), row.outcome, row.id))

    def delete_rows(self, batch_id: int) -> None:
        self.db.execute("DELETE FROM import_rows WHERE batch_id = ?", (batch_id,))

    def rows(self, batch_id: int, actions: list[ImportAction] | None = None, decisions: list[str] | None = None,
             text: str = "", only_issues: bool = False, variants_last: bool = False, limit: int = 200,
             offset: int = 0) -> list[ImportRow]:
        where, params = self._where(batch_id, actions, decisions, text, only_issues)
        order = "(parent_sku <> ''), row_no" if variants_last else "row_no"
        sql = f"SELECT * FROM import_rows{where} ORDER BY {order} LIMIT ? OFFSET ?"
        return [_row(r) for r in self.db.query(sql, (*params, int(limit), max(0, int(offset))))]

    def rows_by_ids(self, batch_id: int, row_ids: list[int]) -> list[ImportRow]:
        found = []
        for start in range(0, len(row_ids), 500):
            chunk = row_ids[start:start + 500]
            marks = ",".join("?" for _ in chunk)
            found += [_row(r) for r in self.db.query(
                f"SELECT * FROM import_rows WHERE batch_id = ? AND id IN ({marks}) ORDER BY row_no", (batch_id, *chunk))]
        return found

    def count_rows(self, batch_id: int, actions: list[ImportAction] | None = None,
                   decisions: list[str] | None = None, text: str = "", only_issues: bool = False) -> int:
        where, params = self._where(batch_id, actions, decisions, text, only_issues)
        return self.db.scalar(f"SELECT COUNT(*) FROM import_rows{where}", tuple(params)) or 0

    @staticmethod
    def _where(batch_id: int, actions, decisions, text: str, only_issues: bool) -> tuple[str, list[Any]]:
        where, params = ["batch_id = ?"], [batch_id]
        if actions:
            where.append(f"action IN ({','.join('?' for _ in actions)})")
            params += [ImportAction(a).value for a in actions]
        if decisions:
            where.append(f"decision IN ({','.join('?' for _ in decisions)})")
            params += list(decisions)
        if text.strip():
            where.append("(sku LIKE ? OR name LIKE ?)")
            params += [f"%{text.strip()}%"] * 2
        if only_issues:
            where.append("issues_json <> '[]'")
        return " WHERE " + " AND ".join(where), params

    def counts_by_action(self, batch_id: int) -> dict[str, int]:
        return {r["action"]: r["n"] for r in self.db.query(
            "SELECT action, COUNT(*) AS n FROM import_rows WHERE batch_id = ? GROUP BY action", (batch_id,))}

    def counts_by_decision(self, batch_id: int) -> dict[str, int]:
        return {r["decision"]: r["n"] for r in self.db.query(
            "SELECT decision, COUNT(*) AS n FROM import_rows WHERE batch_id = ? GROUP BY decision", (batch_id,))}

    def set_decision(self, batch_id: int, row_ids: list[int], decision: str) -> None:
        for start in range(0, len(row_ids), 500):
            chunk = row_ids[start:start + 500]
            marks = ",".join("?" for _ in chunk)
            self.db.execute(f"UPDATE import_rows SET decision = ? WHERE batch_id = ? AND id IN ({marks})",
                            (decision, batch_id, *chunk))

    def set_decision_for_action(self, batch_id: int, action: ImportAction, decision: str) -> None:
        self.db.execute("UPDATE import_rows SET decision = ? WHERE batch_id = ? AND action = ?",
                        (decision, batch_id, ImportAction(action).value))

    def set_outcome(self, row_id: int, outcome: str, product_id: int | None = None) -> None:
        self.db.execute("UPDATE import_rows SET outcome = ?, product_id = COALESCE(?, product_id) WHERE id = ?",
                        (outcome, product_id, row_id))

    def clear_outcomes(self, batch_id: int) -> None:
        self.db.execute("UPDATE import_rows SET outcome = '' WHERE batch_id = ?", (batch_id,))

    # ------------------------------------------------------------------ templates
    def save_template(self, template: ImportTemplate) -> int:
        now = now_iso()
        try:
            cur = self.db.execute(
                "INSERT INTO import_templates (name, target, headers_json, mapping_json, options_json, created_at,"
                " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (name) DO UPDATE SET target = excluded.target,"
                " headers_json = excluded.headers_json, mapping_json = excluded.mapping_json,"
                " options_json = excluded.options_json, updated_at = excluded.updated_at",
                (template.name, template.target, _dump(template.headers), _dump(template.mapping),
                 _dump(template.options), now, now))
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Não foi possível salvar o modelo: {exc}") from exc
        template.id = cur.lastrowid or self.db.scalar("SELECT id FROM import_templates WHERE name = ?",
                                                     (template.name,))
        return template.id  # type: ignore[return-value]

    def templates(self, target: str | None = None) -> list[ImportTemplate]:
        sql, params = "SELECT * FROM import_templates", ()
        if target:
            sql, params = sql + " WHERE target = ?", (target,)
        return [_template(r) for r in self.db.query(sql + " ORDER BY name COLLATE NOCASE", params)]

    def delete_template(self, template_id: int) -> None:
        self.db.execute("DELETE FROM import_templates WHERE id = ?", (template_id,))


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _batch(r: sqlite3.Row) -> ImportBatch:
    return ImportBatch(
        source_name=r["source_name"], format=r["format"], target=r["target"], status=ImportStatus(r["status"]),
        source_path=r["source_path"], source_sha256=r["source_sha256"], mapping=json.loads(r["mapping_json"]),
        options=json.loads(r["options_json"]), counts=json.loads(r["counts_json"]), message=r["message"],
        staging_dir=r["staging_dir"], id=r["id"], created_at=r["created_at"], planned_at=r["planned_at"],
        finished_at=r["finished_at"])


def _row(r: sqlite3.Row) -> ImportRow:
    return ImportRow(
        batch_id=r["batch_id"], row_no=r["row_no"], action=ImportAction(r["action"]), decision=r["decision"],
        sku=r["sku"], name=r["name"], product_id=r["product_id"], parent_sku=r["parent_sku"],
        data=json.loads(r["data_json"]), changes=json.loads(r["changes_json"]), issues=json.loads(r["issues_json"]),
        media=json.loads(r["media_json"]), outcome=r["outcome"], id=r["id"])


def _template(r: sqlite3.Row) -> ImportTemplate:
    return ImportTemplate(name=r["name"], target=r["target"], headers=json.loads(r["headers_json"]),
                          mapping=json.loads(r["mapping_json"]), options=json.loads(r["options_json"]), id=r["id"],
                          created_at=r["created_at"], updated_at=r["updated_at"])
