"""Versioned SQL migrations (persistence/migrations/NNNN_name.sql).

Each file runs in its own transaction together with its bookkeeping row, so a
failing migration leaves the database at the previous version. When an existing
database has pending migrations, a backup is taken first.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from mla.persistence.backup import create_backup
from mla.persistence.db import Database, now_iso

log = logging.getLogger(__name__)
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_NAME_RE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path


def discover(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    found: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        match = _NAME_RE.match(path.name)
        if not match:
            raise MigrationError(f"Nome de migração inválido: {path.name}")
        found.append(Migration(int(match.group(1)), match.group(2), path))
    versions = [m.version for m in found]
    if len(versions) != len(set(versions)):
        raise MigrationError("Versões de migração duplicadas")
    return found


def current_version(db: Database) -> int:
    db.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )
    return db.scalar("SELECT COALESCE(MAX(version), 0) FROM schema_migrations") or 0


def migrate(db: Database, backup_dir: Path | None = None,
            directory: Path = MIGRATIONS_DIR) -> list[int]:
    """Apply pending migrations. Returns the versions applied."""
    existed = db.path.exists() and db.path.stat().st_size > 0
    version = current_version(db)
    pending = [m for m in discover(directory) if m.version > version]
    if not pending:
        return []
    if existed and version > 0 and backup_dir is not None:
        create_backup(db, backup_dir, reason=f"pre-migracao-v{version}")
    conn = db.connect()
    applied: list[int] = []
    for migration in pending:
        sql = migration.path.read_text(encoding="utf-8")
        bookkeeping = (
            "INSERT INTO schema_migrations (version, name, applied_at) "
            f"VALUES ({migration.version}, '{migration.name}', '{now_iso()}');"
        )
        try:
            conn.executescript(f"BEGIN IMMEDIATE;\n{sql}\n{bookkeeping}\nCOMMIT;")
        except Exception as exc:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise MigrationError(f"Falha na migração {migration.path.name}: {exc}") from exc
        log.info("migração aplicada: %04d_%s", migration.version, migration.name)
        applied.append(migration.version)
    return applied
