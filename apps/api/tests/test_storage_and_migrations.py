from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from mla_api.storage import LocalStorage, StorageError, make_key

ORG_A, ORG_B = uuid.uuid4(), uuid.uuid4()


def test_keys_are_scoped_to_the_owner(tmp_path):
    s = LocalStorage(tmp_path)
    key = s.put(ORG_A, "exports", "lote-1.xlsx", b"data")
    assert key == f"orgs/{ORG_A}/exports/lote-1.xlsx"
    assert s.read(ORG_A, key) == b"data"
    with pytest.raises(PermissionError):
        s.read(ORG_B, key)
    with pytest.raises(PermissionError):
        s.delete(ORG_B, key)


@pytest.mark.parametrize("name", ["../x", "..", "a/b", "a\\b", ".hidden", "", "x" * 200, "c:evil", "a\x00b"])
def test_unsafe_names_refused(tmp_path, name):
    with pytest.raises(StorageError):
        LocalStorage(tmp_path).put(ORG_A, "imports", name, b"x")


def test_crafted_keys_refused(tmp_path):
    s = LocalStorage(tmp_path)
    for key in (f"orgs/{ORG_A}/../{ORG_B}/exports/x", f"orgs/{ORG_A}/secret/x", f"orgs/{ORG_A}/exports/a/b"):
        with pytest.raises((StorageError, PermissionError)):
            s.read(ORG_A, key)
    with pytest.raises(StorageError):
        make_key(ORG_A, "public", "x")


def test_write_failure_leaves_no_partial_file(tmp_path, monkeypatch):
    s = LocalStorage(tmp_path)

    def boom(self, data):
        raise OSError("disco cheio")
    monkeypatch.setattr(Path, "write_bytes", boom)
    with pytest.raises(StorageError):
        s.put(ORG_A, "exports", "x.xlsx", b"data")
    assert not list(tmp_path.rglob("x.xlsx*"))


def test_alembic_migration_matches_models(tmp_path):
    """The hand-written migration creates exactly what the models declare (SQLite)."""
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext

    from mla_api.db import Base, make_engine
    url = f"sqlite:///{(tmp_path / 'mig.db').as_posix()}"
    cfg = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    cfg.attributes["database_url"] = url
    command.upgrade(cfg, "head")
    engine = make_engine(url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == []
    command.downgrade(cfg, "base")
