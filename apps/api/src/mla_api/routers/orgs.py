from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mla_api import audit
from mla_api.deps import Auth, OrgContext, current_auth, get_db, require
from mla_api.models import AuditEvent, Membership, Role, User
from mla_api.routers.auth import create_organization
from mla_api.schemas import AuditOut, MemberAddIn, MemberOut, MemberRoleIn, OrgCreateIn, OrgOut, UserOut

router = APIRouter(prefix="/api/orgs", tags=["organizations"])


@router.post("", response_model=OrgOut, status_code=201)
def create_org(body: OrgCreateIn, auth: Auth = Depends(current_auth), db: Session = Depends(get_db)) -> OrgOut:
    org = create_organization(db, body.name, auth.user)
    db.commit()
    return OrgOut.model_validate(org)


@router.get("/{org_id}", response_model=OrgOut)
def get_org(ctx: OrgContext = Depends(require("catalog.read"))) -> OrgOut:
    return OrgOut.model_validate(ctx.org)


def _member_out(m: Membership) -> MemberOut:
    return MemberOut(user=UserOut.model_validate(m.user), role=m.role, created_at=m.created_at)


@router.get("/{org_id}/members", response_model=list[MemberOut])
def list_members(ctx: OrgContext = Depends(require("members.read"))) -> list[MemberOut]:
    rows = ctx.db.scalars(select(Membership).where(Membership.organization_id == ctx.org_id)
                          .order_by(Membership.created_at)).all()
    return [_member_out(m) for m in rows]


def _guard_role_change(ctx: OrgContext, target: Membership | None, new_role: str | None) -> None:
    """Only owners grant or touch the owner role, and an organization never loses its last owner."""
    touches_owner = new_role == Role.OWNER or (target is not None and target.role == Role.OWNER)
    if touches_owner and ctx.role != Role.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas proprietários alteram proprietários.")
    if target is not None and target.role == Role.OWNER and new_role != Role.OWNER:
        owners = ctx.db.scalar(select(func.count()).select_from(Membership).where(
            Membership.organization_id == ctx.org_id, Membership.role == Role.OWNER))
        if owners <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "A organização precisa de pelo menos um proprietário.")


@router.post("/{org_id}/members", response_model=MemberOut, status_code=201)
def add_member(body: MemberAddIn, ctx: OrgContext = Depends(require("members.manage"))) -> MemberOut:
    """Adds an existing account. E-mail invitations for people without an account are a later item."""
    _guard_role_change(ctx, None, body.role)
    user = ctx.db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nenhuma conta com este e-mail. Peça que a pessoa se cadastre.")
    if ctx.db.scalar(select(Membership.id).where(Membership.organization_id == ctx.org_id,
                                                 Membership.user_id == user.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta pessoa já é membro da organização.")
    m = Membership(organization_id=ctx.org_id, user_id=user.id, role=body.role)
    ctx.db.add(m)
    audit.record(ctx.db, "member.added", user_id=ctx.user.id, org_id=ctx.org_id, target_type="user",
                 target_id=user.id, role=str(body.role))
    ctx.db.commit()
    ctx.db.refresh(m)
    return _member_out(m)


def _target(ctx: OrgContext, user_id: uuid.UUID) -> Membership:
    m = ctx.db.scalar(select(Membership).where(Membership.organization_id == ctx.org_id,
                                               Membership.user_id == user_id))
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membro não encontrado.")
    return m


@router.patch("/{org_id}/members/{user_id}", response_model=MemberOut)
def change_role(user_id: uuid.UUID, body: MemberRoleIn,
                ctx: OrgContext = Depends(require("members.manage"))) -> MemberOut:
    m = _target(ctx, user_id)
    _guard_role_change(ctx, m, body.role)
    old = m.role
    m.role = body.role
    audit.record(ctx.db, "member.role_changed", user_id=ctx.user.id, org_id=ctx.org_id, target_type="user",
                 target_id=user_id, old=old, new=str(body.role))
    ctx.db.commit()
    return _member_out(m)


@router.delete("/{org_id}/members/{user_id}", status_code=204, response_class=Response, response_model=None)
def remove_member(user_id: uuid.UUID, ctx: OrgContext = Depends(require("members.manage"))) -> None:
    m = _target(ctx, user_id)
    _guard_role_change(ctx, m, None)
    ctx.db.delete(m)
    audit.record(ctx.db, "member.removed", user_id=ctx.user.id, org_id=ctx.org_id, target_type="user",
                 target_id=user_id)
    ctx.db.commit()


def recent_audit(ctx: OrgContext, limit: int) -> list[AuditOut]:
    rows = ctx.db.execute(
        select(AuditEvent, User.name).outerjoin(User, User.id == AuditEvent.user_id)
        .where(AuditEvent.organization_id == ctx.org_id)
        .order_by(AuditEvent.created_at.desc()).limit(limit)).all()
    return [AuditOut.model_validate(ev).model_copy(update={"user_name": name}) for ev, name in rows]


@router.get("/{org_id}/audit", response_model=list[AuditOut])
def list_audit(limit: int = 50, ctx: OrgContext = Depends(require("audit.read"))) -> list[AuditOut]:
    return recent_audit(ctx, max(1, min(limit, 200)))
