from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from mla_api.models import AuditEvent


def record(db: Session, action: str, *, user_id: uuid.UUID | None = None, org_id: uuid.UUID | None = None,
           target_type: str = "", target_id: object = "", **details) -> None:
    """Adds an audit row to the current transaction. Never pass passwords or tokens in details."""
    db.add(AuditEvent(organization_id=org_id, user_id=user_id, action=action, target_type=target_type,
                      target_id=str(target_id) if target_id else "", details=details))
