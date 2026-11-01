"""Request dependencies: database session, authenticated user and organization context."""
from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from mla_api.db import as_aware, set_tenant, utcnow
from mla_api.models import AuthSession, Membership, Organization, User
from mla_api.security import has_permission, hash_token
from mla_api.settings import Settings


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.sessionmaker()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@dataclass
class Auth:
    user: User
    session: AuthSession


def current_auth(request: Request, db: Session = Depends(get_db)) -> Auth:
    settings: Settings = request.app.state.settings
    token = request.cookies.get(settings.session_cookie)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Faça login para continuar.")
    sess = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    now = utcnow()
    if sess is None or as_aware(sess.expires_at) <= now or not sess.user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada. Faça login novamente.")
    # Sliding expiry: renewed once less than half of the lifetime is left.
    ttl = timedelta(hours=settings.session_ttl_hours)
    if as_aware(sess.expires_at) - now < ttl / 2:
        sess.expires_at = now + ttl
        db.commit()
    return Auth(user=sess.user, session=sess)


@dataclass
class OrgContext:
    org: Organization
    membership: Membership
    user: User
    db: Session

    @property
    def org_id(self) -> uuid.UUID:
        return self.org.id

    @property
    def role(self) -> str:
        return self.membership.role


def org_context(org_id: uuid.UUID, auth: Auth = Depends(current_auth), db: Session = Depends(get_db)) -> OrgContext:
    membership = db.scalar(select(Membership).where(Membership.organization_id == org_id,
                                                    Membership.user_id == auth.user.id))
    if membership is None:
        # 404, not 403: a non-member must not learn whether the organization exists.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organização não encontrada.")
    set_tenant(db, org_id)
    return OrgContext(org=membership.organization, membership=membership, user=auth.user, db=db)


def require(permission: str) -> Callable[..., OrgContext]:
    def checker(ctx: OrgContext = Depends(org_context)) -> OrgContext:
        if not has_permission(ctx.role, permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Seu papel nesta organização não permite esta ação.")
        return ctx
    return checker
