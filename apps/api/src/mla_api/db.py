"""Engine, sessions and the tenant context.

Tenant isolation has two layers:
1. Application: every organization-owned query goes through an OrgContext and filters by organization_id.
2. PostgreSQL row-level security: the session carries ``app.org_id`` (transaction-local), and the policies in
   migration 0001 hide rows of other organizations even if a query forgets the filter.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

TENANT_KEY = "org_id"


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_aware(value: datetime) -> datetime:
    """SQLite returns naive datetimes; everything stored is UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

        return engine
    return create_engine(url, pool_pre_ping=True)


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def _set_pg_tenant(connection, org_id: uuid.UUID | None) -> None:
    if connection.dialect.name == "postgresql":
        connection.execute(text("select set_config('app.org_id', :v, true)"),
                           {"v": str(org_id) if org_id else ""})


@event.listens_for(Session, "after_begin")
def _apply_tenant(session: Session, _transaction, connection) -> None:
    # set_config(..., true) lasts one transaction, so it is re-applied after every commit.
    org_id = session.info.get(TENANT_KEY)
    if org_id:
        _set_pg_tenant(connection, org_id)


def set_tenant(session: Session, org_id: uuid.UUID) -> None:
    session.info[TENANT_KEY] = org_id
    if session.in_transaction():
        _set_pg_tenant(session.connection(), org_id)
