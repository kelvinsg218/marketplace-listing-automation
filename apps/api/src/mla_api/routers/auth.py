from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mla_api import audit
from mla_api.db import as_aware, set_tenant, utcnow
from mla_api.deps import Auth, current_auth, get_db
from mla_api.models import AuthSession, Membership, Organization, PasswordResetToken, Role, User
from mla_api.schemas import (LoginIn, MembershipOut, MeOut, OrgOut, RegisterIn, ResetConfirmIn, ResetRequestIn,
                             UserOut)
from mla_api.security import hash_password, hash_token, new_token, password_problem, verify_password
from mla_api.settings import Settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


def slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "empresa"


def create_organization(db: Session, name: str, owner: User) -> Organization:
    base = slugify(name)
    slug = base
    while db.scalar(select(Organization.id).where(Organization.slug == slug)):
        slug = f"{base}-{uuid.uuid4().hex[:6]}"
    org = Organization(name=name.strip(), slug=slug)
    db.add(org)
    db.flush()
    set_tenant(db, org.id)  # the audit row below is organization-owned (RLS WITH CHECK)
    db.add(Membership(organization_id=org.id, user_id=owner.id, role=Role.OWNER))
    audit.record(db, "org.created", user_id=owner.id, org_id=org.id, target_type="organization", target_id=org.id)
    return org


def _start_session(db: Session, response: Response, request: Request, user: User) -> None:
    settings: Settings = request.app.state.settings
    token = new_token()
    db.add(AuthSession(user_id=user.id, token_hash=hash_token(token),
                       expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
                       user_agent=(request.headers.get("user-agent") or "")[:200]))
    response.set_cookie(settings.session_cookie, token, max_age=settings.session_ttl_hours * 3600,
                        httponly=True, secure=settings.cookie_secure, samesite="lax", path="/")


def _me(db: Session, user: User) -> MeOut:
    rows = db.scalars(select(Membership).where(Membership.user_id == user.id)
                      .order_by(Membership.created_at)).all()
    return MeOut(user=UserOut.model_validate(user),
                 memberships=[MembershipOut(organization=OrgOut.model_validate(m.organization), role=m.role)
                              for m in rows])


@router.post("/register", response_model=MeOut, status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)) -> MeOut:
    settings: Settings = request.app.state.settings
    if not settings.allow_signup:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cadastro aberto desativado nesta instalação.")
    if problem := password_problem(body.password):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma conta com este e-mail.")
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    create_organization(db, body.organization_name, user)
    audit.record(db, "auth.registered", user_id=user.id, target_type="user", target_id=user.id)
    _start_session(db, response, request, user)
    db.commit()
    return _me(db, user)


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> MeOut:
    limiter = request.app.state.login_limiter
    email = body.email.lower()
    keys = (f"email:{email}", f"ip:{request.client.host if request.client else '?'}")
    if limiter.blocked(*keys):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Muitas tentativas. Aguarde alguns minutos e tente novamente.")
    user = db.scalar(select(User).where(User.email == email))
    if not verify_password(user.password_hash if user else None, body.password) or not user.is_active:
        limiter.fail(*keys)
        audit.record(db, "auth.login_failed", user_id=user.id if user else None)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha incorretos.")
    limiter.reset(keys[0])
    user.last_login_at = utcnow()
    _start_session(db, response, request, user)
    audit.record(db, "auth.login", user_id=user.id)
    db.commit()
    return _me(db, user)


@router.post("/logout", status_code=204, response_class=Response, response_model=None)
def logout(request: Request, response: Response, auth: Auth = Depends(current_auth),
           db: Session = Depends(get_db)) -> None:
    db.execute(delete(AuthSession).where(AuthSession.id == auth.session.id))
    audit.record(db, "auth.logout", user_id=auth.user.id)
    db.commit()
    response.delete_cookie(request.app.state.settings.session_cookie, path="/")


@router.get("/me", response_model=MeOut)
def me(auth: Auth = Depends(current_auth), db: Session = Depends(get_db)) -> MeOut:
    return _me(db, auth.user)


@router.post("/password-reset/request", status_code=202)
def reset_request(body: ResetRequestIn, request: Request, db: Session = Depends(get_db)) -> dict:
    """Always answers 202, whether or not the e-mail exists (no account enumeration)."""
    settings: Settings = request.app.state.settings
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user and user.is_active:
        token = new_token()
        db.add(PasswordResetToken(user_id=user.id, token_hash=hash_token(token),
                                  expires_at=utcnow() + timedelta(minutes=settings.reset_token_ttl_minutes)))
        audit.record(db, "auth.reset_requested", user_id=user.id)
        db.commit()
        # Token in the URL fragment: browsers never send it to servers or proxies, so it stays out of access logs.
        link = f"{settings.public_url.rstrip('/')}/redefinir-senha/#token={token}"
        request.app.state.mailer.send(
            user.email, "MLA — redefinição de senha",
            f"Para criar uma nova senha, abra o link abaixo (válido por {settings.reset_token_ttl_minutes} "
            f"minutos):\n\n{link}\n\nSe você não pediu, ignore esta mensagem.")
    return {"detail": "Se o e-mail estiver cadastrado, enviaremos as instruções."}


@router.post("/password-reset/confirm", status_code=204, response_class=Response, response_model=None)
def reset_confirm(body: ResetConfirmIn, db: Session = Depends(get_db)) -> None:
    if problem := password_problem(body.password):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)
    row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(body.token)))
    if row is None or row.used_at is not None or as_aware(row.expires_at) <= utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Link inválido ou expirado. Peça um novo.")
    user = db.get(User, row.user_id)
    user.password_hash = hash_password(body.password)
    row.used_at = utcnow()
    # A password reset ends every open session of the account.
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    audit.record(db, "auth.password_reset", user_id=user.id)
    db.commit()
