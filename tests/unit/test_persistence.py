import shutil
import sqlite3

import pytest

from mla.persistence.backup import create_backup, list_backups, prune_backups, restore_backup
from mla.persistence.db import Database
from mla.persistence.migrator import MIGRATIONS_DIR, MigrationError, current_version, discover, migrate

EXPECTED_TABLES = {
    "products", "product_images", "product_variants", "product_marketplace_data", "product_groups",
    "group_products", "marketplace_accounts", "automation_jobs", "automation_job_items", "listings",
    "execution_logs", "application_settings", "license_state", "schema_migrations",
}


def test_fresh_database_has_full_schema(tmp_path):
    db = Database(tmp_path / "t.db")
    applied = migrate(db)
    assert applied == [m.version for m in discover()]
    tables = {r[0] for r in db.query("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert EXPECTED_TABLES <= tables
    assert db.scalar("PRAGMA foreign_keys") == 1
    assert db.scalar("PRAGMA journal_mode") == "wal"
    assert db.scalar("SELECT COUNT(*) FROM marketplace_accounts") == 3
    assert migrate(db) == []  # idempotent
    db.close()


def test_failed_migration_rolls_back_and_keeps_version(tmp_path):
    mig_dir = tmp_path / "migs"
    shutil.copytree(MIGRATIONS_DIR, mig_dir)
    db = Database(tmp_path / "t.db")
    migrate(db, directory=mig_dir)
    version = current_version(db)
    (mig_dir / "9999_broken.sql").write_text(
        "CREATE TABLE half_done (id INTEGER);\nINSERT INTO no_such_table VALUES (1);", encoding="utf-8")
    with pytest.raises(MigrationError):
        migrate(db, directory=mig_dir)
    assert current_version(db) == version
    assert db.query_one("SELECT name FROM sqlite_master WHERE name = 'half_done'") is None
    db.close()


def test_pending_migration_on_existing_db_takes_backup(tmp_path):
    mig_dir = tmp_path / "migs"
    shutil.copytree(MIGRATIONS_DIR, mig_dir)
    db = Database(tmp_path / "t.db")
    migrate(db, directory=mig_dir)
    (mig_dir / "9000_extra.sql").write_text("CREATE TABLE extra (id INTEGER);", encoding="utf-8")
    backups = tmp_path / "bk"
    assert migrate(db, backup_dir=backups, directory=mig_dir) == [9000]
    assert len(list_backups(backups)) == 1
    db.close()


def test_transaction_rolls_back_on_error(tmp_path):
    db = Database(tmp_path / "t.db")
    migrate(db)
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction() as conn:
            conn.execute("INSERT INTO application_settings VALUES ('a', '1', 'x')")
            with db.transaction() as inner:  # nested joins the outer transaction
                inner.execute("INSERT INTO application_settings VALUES ('a', '2', 'x')")
    assert db.scalar("SELECT COUNT(*) FROM application_settings") == 0
    db.close()


def test_backup_restore_and_prune(tmp_path):
    db = Database(tmp_path / "t.db")
    migrate(db)
    db.execute("INSERT INTO application_settings VALUES ('k', '\"before\"', 'x')")
    backup_dir = tmp_path / "bk"
    snapshot = create_backup(db, backup_dir, reason="teste")
    db.execute("UPDATE application_settings SET value_json = '\"after\"'")
    safety = restore_backup(db, snapshot, backup_dir)
    assert safety.exists()
    assert db.scalar("SELECT value_json FROM application_settings WHERE key = 'k'") == '"before"'
    for _ in range(4):
        create_backup(db, backup_dir, reason="x")
    prune_backups(backup_dir, keep=3)
    assert len(list_backups(backup_dir)) == 3
    db.close()


def test_restore_rejects_corrupt_file(tmp_path):
    db = Database(tmp_path / "t.db")
    migrate(db)
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"not a database" * 100)
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        restore_backup(db, bad, tmp_path / "bk")
    db.close()
