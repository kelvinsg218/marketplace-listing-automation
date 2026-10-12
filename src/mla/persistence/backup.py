"""Online SQLite backups using the sqlite3 backup API (safe while the app runs)."""
from __future__ import annotations

import logging
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mla.persistence.db import Database

log = logging.getLogger(__name__)
KEEP_DEFAULT = 15
_SAFE = re.compile(r"[^a-z0-9-]+")


def create_backup(db: "Database", backup_dir: Path, reason: str = "manual",
                  keep: int = KEEP_DEFAULT) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = backup_dir / f"mla-{stamp}-{_SAFE.sub('-', reason.lower()).strip('-')}.db"
    dest = sqlite3.connect(target)
    try:
        db.connect().backup(dest)
    finally:
        dest.close()
    log.info("backup criado: %s", target.name)
    prune_backups(backup_dir, keep)
    return target


def list_backups(backup_dir: Path) -> list[Path]:
    if not backup_dir.exists():
        return []
    return sorted(backup_dir.glob("mla-*.db"), key=lambda p: p.name, reverse=True)


def prune_backups(backup_dir: Path, keep: int = KEEP_DEFAULT) -> None:
    for old in list_backups(backup_dir)[keep:]:
        old.unlink(missing_ok=True)


def restore_backup(db: "Database", backup: Path, backup_dir: Path) -> Path:
    """Replace the live database with a backup. A safety backup is taken first.

    All connections are closed; callers must reopen services afterwards.
    """
    if not backup.exists():
        raise FileNotFoundError(backup)
    check = sqlite3.connect(backup)
    try:
        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("O arquivo de backup está corrompido")
    finally:
        check.close()
    safety = create_backup(db, backup_dir, reason="antes-de-restaurar")
    db.close()
    for suffix in ("-wal", "-shm"):
        Path(str(db.path) + suffix).unlink(missing_ok=True)
    shutil.copyfile(backup, db.path)
    log.info("backup restaurado: %s (segurança: %s)", backup.name, safety.name)
    return safety
