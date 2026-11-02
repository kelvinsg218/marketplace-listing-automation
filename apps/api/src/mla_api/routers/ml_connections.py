"""Mercado Livre official OAuth: connect a seller account, identify it, keep tokens fresh, disconnect (D-036).

Separate from the XLSX flow: a connection never sends the bulk-listing sheet (the seller still uploads it on the
Mercado Livre site) and nothing here publishes listings. See services/ml_oauth.py for the official endpoints.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mla_api import audit
from mla_api.db import as_aware, utcnow
from mla_api.deps import OrgContext, current_auth, get_db, org_context, require
from mla_api.models import ConnectionStatus, MarketplaceConnection, OAuthState, SellerAccount
from mla_api.schemas import UtcDatetime
from mla_api.security import has_permission
from mla_api.services.ml_oauth import MLAuthError, MLOAuthClient, Tokens, pkce_pair
from mla_api.services.token_crypto import TokenCipher, TokenCryptoError

router = APIRouter(tags=["mercadolivre-oauth"])
MARKETPLACE = "mercadolivre"
STATE_TTL = timedelta(minutes=10)
REFRESH_MARGIN = timedelta(minutes=5)


# --- setup ------------------------------------------------------------------------------------------------------
def setup_problem(settings) -> str | None:
    missing = [name for name, value in (
        ("MLA_ML_CLIENT_ID", settings.ml_client_id), ("MLA_ML_CLIENT_SECRET", settings.ml_client_secret.get_secret_value()),
        ("MLA_ML_REDIRECT_URI", settings.ml_redirect_uri),
        ("MLA_TOKEN_ENCRYPTION_KEY", settings.token_encryption_key.get_secret_value())) if not value.strip()]
    if missing:
        return ("Integração oficial com o Mercado Livre não configurada no servidor (faltam: " + ", ".join(missing)
                + "). Crie o aplicativo no portal de desenvolvedores do Mercado Livre e configure as variáveis.")
    try:
        TokenCipher(settings.token_encryption_key.get_secret_value().strip())
    except TokenCryptoError as exc:
        return str(exc)
    return None


def _tools(request: Request) -> tuple[MLOAuthClient, TokenCipher]:
    st = request.app.state.settings
    problem = setup_problem(st)
    if problem:
        raise HTTPException(status.HTTP_409_CONFLICT, problem)
    client = MLOAuthClient(st.ml_client_id.strip(), st.ml_client_secret.get_secret_value().strip(),
                           st.ml_redirect_uri.strip(), getattr(request.app.state, "ml_transport", None))
    return client, TokenCipher(st.token_encryption_key.get_secret_value().strip())


def _aad(conn: MarketplaceConnection, field: str) -> str:
    return f"{conn.organization_id}:{conn.seller_account_id}:{field}"


def _store_tokens(conn: MarketplaceConnection, cipher: TokenCipher, t: Tokens) -> None:
    conn.access_token_enc = cipher.encrypt(t.access_token, _aad(conn, "access"))
    if t.refresh_token:  # single use: always keep the newest one
        conn.refresh_token_enc = cipher.encrypt(t.refresh_token, _aad(conn, "refresh"))
    conn.expires_at = utcnow() + timedelta(seconds=max(0, t.expires_in))
    conn.scope = t.scope[:255]
    conn.status, conn.last_error = ConnectionStatus.CONNECTED, ""


def _wipe(conn: MarketplaceConnection, new_status: str, error: str = "") -> None:
    conn.access_token_enc = conn.refresh_token_enc = ""
    conn.expires_at = None
    conn.status, conn.last_error = new_status, error[:300]


def ensure_access_token(db: Session, conn: MarketplaceConnection, client: MLOAuthClient, cipher: TokenCipher,
                        *, force: bool = False) -> str:
    """A valid access token, refreshing it when it is about to expire. The row is locked during the refresh
    (PostgreSQL FOR UPDATE) because a refresh token works only once. Commits."""
    # populate_existing: after waiting for the lock, read what a concurrent refresh may have just written.
    conn = db.scalar(select(MarketplaceConnection).where(MarketplaceConnection.id == conn.id).with_for_update()
                     .execution_options(populate_existing=True))
    if not conn.access_token_enc:
        raise MLAuthError("Conta não conectada.", reauth=True)
    if not force and conn.expires_at and as_aware(conn.expires_at) - REFRESH_MARGIN > utcnow():
        return cipher.decrypt(conn.access_token_enc, _aad(conn, "access"))
    if not conn.refresh_token_enc:
        _wipe(conn, ConnectionStatus.NEEDS_REAUTH, "Sem refresh token (ative offline_access no aplicativo).")
        db.commit()
        raise MLAuthError(conn.last_error, reauth=True)
    try:
        t = client.refresh(cipher.decrypt(conn.refresh_token_enc, _aad(conn, "refresh")))
    except MLAuthError as exc:
        if exc.reauth:
            _wipe(conn, ConnectionStatus.NEEDS_REAUTH, "Autorização revogada ou expirada; conecte a conta novamente.")
            audit.record(db, "ml.reauth_needed", org_id=conn.organization_id, target_type="seller_account",
                         target_id=conn.seller_account_id)
        else:
            conn.status, conn.last_error = ConnectionStatus.ERROR, str(exc)[:300]
        db.commit()
        raise
    _store_tokens(conn, cipher, t)
    conn.refreshed_at = utcnow()
    audit.record(db, "ml.token_refreshed", org_id=conn.organization_id, target_type="seller_account",
                 target_id=conn.seller_account_id)
    db.commit()
    return t.access_token


# --- read -------------------------------------------------------------------------------------------------------
class ConnectionOut(BaseModel):
    seller_account_id: uuid.UUID
    label: str
    external_id: str
    status: str
    nickname: str = ""
    remote_user_id: str = ""
    expires_at: UtcDatetime | None = None
    connected_at: UtcDatetime | None = None
    checked_at: UtcDatetime | None = None
    last_error: str = ""


def _connection(ctx: OrgContext, account_id: uuid.UUID) -> tuple[SellerAccount, MarketplaceConnection | None]:
    a = ctx.db.scalar(select(SellerAccount).where(SellerAccount.id == account_id,
                                                  SellerAccount.organization_id == ctx.org_id))
    if a is None or a.marketplace != MARKETPLACE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conta de vendedor não encontrada.")
    conn = ctx.db.scalar(select(MarketplaceConnection).where(MarketplaceConnection.organization_id == ctx.org_id,
                                                             MarketplaceConnection.seller_account_id == a.id))
    return a, conn


def _out(a: SellerAccount, c: MarketplaceConnection | None) -> ConnectionOut:
    if c is None:
        return ConnectionOut(seller_account_id=a.id, label=a.label, external_id=a.external_id, status="not_connected")
    return ConnectionOut(seller_account_id=a.id, label=a.label, external_id=a.external_id, status=c.status,
                         nickname=c.nickname, remote_user_id=c.remote_user_id or "", expires_at=c.expires_at,
                         connected_at=c.connected_at, checked_at=c.checked_at, last_error=c.last_error)


@router.get("/api/orgs/{org_id}/integrations/mercadolivre")
def integration_status(request: Request, ctx: OrgContext = Depends(require("catalog.read"))) -> dict:
    st = request.app.state.settings
    accounts = ctx.db.scalars(select(SellerAccount).where(SellerAccount.organization_id == ctx.org_id,
                                                          SellerAccount.marketplace == MARKETPLACE)
                              .order_by(SellerAccount.label)).all()
    conns = {c.seller_account_id: c for c in ctx.db.scalars(select(MarketplaceConnection).where(
        MarketplaceConnection.organization_id == ctx.org_id))}
    problem = setup_problem(st)
    return {"configured": problem is None, "message": problem,
            "redirect_uri": st.ml_redirect_uri.strip() or None,
            "accounts": [_out(a, conns.get(a.id)).model_dump(mode="json") for a in accounts]}


# --- connect ----------------------------------------------------------------------------------------------------
@router.post("/api/orgs/{org_id}/seller-accounts/{account_id}/oauth/start")
def start(account_id: uuid.UUID, request: Request, ctx: OrgContext = Depends(require("members.manage"))) -> dict:
    """Returns the official authorization URL; the browser goes there and the seller logs in on Mercado Livre
    (the MLA never sees the password)."""
    client, cipher = _tools(request)
    a, _ = _connection(ctx, account_id)
    ctx.db.execute(delete(OAuthState).where(OAuthState.organization_id == ctx.org_id, OAuthState.expires_at < utcnow()))
    state = f"{ctx.org_id.hex}.{secrets.token_urlsafe(32)}"
    verifier, challenge = pkce_pair()
    s = OAuthState(organization_id=ctx.org_id, seller_account_id=a.id, user_id=ctx.user.id,
                   state_hash=hashlib.sha256(state.encode()).hexdigest(), expires_at=utcnow() + STATE_TTL,
                   verifier_enc=cipher.encrypt(verifier, f"{ctx.org_id}:{a.id}:pkce"))
    ctx.db.add(s)
    audit.record(ctx.db, "ml.authorization_started", user_id=ctx.user.id, org_id=ctx.org_id,
                 target_type="seller_account", target_id=a.id)
    ctx.db.commit()
    return {"authorization_url": client.authorization_url(state, challenge)}


def _back(request: Request, result: str) -> RedirectResponse:
    return RedirectResponse(f"{request.app.state.settings.public_url.rstrip('/')}/marketplaces/?ml={result}", 303)


@router.get("/api/integrations/mercadolivre/callback", include_in_schema=False)
def callback(request: Request, state: str = "", code: str = "", error: str = "",
             db: Session = Depends(get_db)) -> RedirectResponse:
    """Where Mercado Livre sends the browser back. The organization comes from the state, and the state must have
    been created by the same logged-in user less than 10 minutes ago (single use)."""
    try:
        auth = current_auth(request, db)
        org_id = uuid.UUID(hex=state.split(".", 1)[0])
        ctx = org_context(org_id, request, auth, db)
    except (HTTPException, ValueError):
        return _back(request, "sessao")
    if not has_permission(ctx.role, "members.manage"):
        return _back(request, "sem_permissao")
    s = db.scalar(select(OAuthState).where(OAuthState.organization_id == org_id,
                                           OAuthState.state_hash == hashlib.sha256(state.encode()).hexdigest()))
    if s is None or s.used_at or s.user_id != auth.user.id or as_aware(s.expires_at) < utcnow():
        return _back(request, "expirado")
    s.used_at = utcnow()
    db.commit()  # single use, even if what follows fails
    account_id = s.seller_account_id
    if error or not code:
        audit.record(db, "ml.authorization_denied", user_id=auth.user.id, org_id=org_id,
                     target_type="seller_account", target_id=account_id, reason=error[:60])
        db.commit()
        return _back(request, "negado")
    try:
        client, cipher = _tools(request)
        a, conn = _connection(ctx, account_id)
        tokens = client.exchange(code, cipher.decrypt(s.verifier_enc, f"{org_id}:{account_id}:pkce"))
        me = client.me(tokens.access_token)
    except (HTTPException, MLAuthError, TokenCryptoError) as exc:
        audit.record(db, "ml.connection_failed", user_id=auth.user.id, org_id=org_id, target_type="seller_account",
                     target_id=account_id, error=str(getattr(exc, "detail", exc))[:200])
        db.commit()
        return _back(request, "erro")
    remote = me["id"] or tokens.user_id
    if a.external_id and a.external_id != remote:
        audit.record(db, "ml.connection_refused", user_id=auth.user.id, org_id=org_id, target_type="seller_account",
                     target_id=a.id, reason="different_account", remote_user_id=remote)
        db.commit()
        return _back(request, "conta_diferente")
    if conn is None:
        conn = MarketplaceConnection(organization_id=org_id, seller_account_id=a.id, marketplace=MARKETPLACE)
        db.add(conn)
    conn.remote_user_id, conn.nickname = remote, me["nickname"][:120]
    conn.connected_by, conn.connected_at, conn.checked_at = auth.user.id, utcnow(), utcnow()
    _store_tokens(conn, cipher, tokens)
    if not a.external_id:
        a.external_id = remote[:40]
    audit.record(db, "ml.connected", user_id=auth.user.id, org_id=org_id, target_type="seller_account",
                 target_id=a.id, remote_user_id=remote, nickname=conn.nickname)
    try:
        db.commit()
    except IntegrityError:  # this Mercado Livre account is already linked to another seller account here
        db.rollback()
        return _back(request, "ja_conectada")
    return _back(request, "conectado")


# --- maintain ---------------------------------------------------------------------------------------------------
def _connected(ctx: OrgContext, account_id: uuid.UUID) -> tuple[SellerAccount, MarketplaceConnection]:
    a, conn = _connection(ctx, account_id)
    if conn is None or not conn.access_token_enc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta conta não está conectada ao Mercado Livre.")
    return a, conn


def _fail(exc: MLAuthError) -> HTTPException:
    if exc.reauth:
        return HTTPException(status.HTTP_409_CONFLICT, "A autorização foi revogada ou expirou; conecte a conta novamente.")
    return HTTPException(status.HTTP_502_BAD_GATEWAY, f"Mercado Livre: {exc}")


@router.post("/api/orgs/{org_id}/seller-accounts/{account_id}/oauth/check", response_model=ConnectionOut)
def check(account_id: uuid.UUID, request: Request, ctx: OrgContext = Depends(require("members.manage"))) -> ConnectionOut:
    """Confirms the connection with GET /users/me (renewing the token first when needed)."""
    client, cipher = _tools(request)
    a, conn = _connected(ctx, account_id)
    try:
        me = client.me(ensure_access_token(ctx.db, conn, client, cipher))
    except MLAuthError as exc:
        if not exc.reauth and conn.status == ConnectionStatus.CONNECTED:
            conn.status, conn.last_error = ConnectionStatus.ERROR, str(exc)[:300]
            ctx.db.commit()
        raise _fail(exc)
    if me["id"] and me["id"] != conn.remote_user_id:
        _wipe(conn, ConnectionStatus.NEEDS_REAUTH, "O token pertence a outra conta do Mercado Livre.")
    else:
        conn.status, conn.last_error, conn.nickname = ConnectionStatus.CONNECTED, "", me["nickname"][:120] or conn.nickname
    conn.checked_at = utcnow()
    ctx.db.commit()
    return _out(a, conn)


@router.post("/api/orgs/{org_id}/seller-accounts/{account_id}/oauth/refresh", response_model=ConnectionOut)
def refresh(account_id: uuid.UUID, request: Request, ctx: OrgContext = Depends(require("members.manage"))) -> ConnectionOut:
    client, cipher = _tools(request)
    a, conn = _connected(ctx, account_id)
    try:
        ensure_access_token(ctx.db, conn, client, cipher, force=True)
    except MLAuthError as exc:
        raise _fail(exc)
    return _out(*_connection(ctx, account_id))


@router.post("/api/orgs/{org_id}/seller-accounts/{account_id}/oauth/disconnect", response_model=ConnectionOut)
def disconnect(account_id: uuid.UUID, ctx: OrgContext = Depends(require("members.manage"))) -> ConnectionOut:
    """Erases the tokens in the MLA. Removing the app's permission on the Mercado Livre side is done by the seller
    in their Mercado Livre account (no revocation endpoint is used here)."""
    a, conn = _connection(ctx, account_id)
    if conn is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta conta não está conectada ao Mercado Livre.")
    _wipe(conn, ConnectionStatus.DISCONNECTED)
    audit.record(ctx.db, "ml.disconnected", user_id=ctx.user.id, org_id=ctx.org_id, target_type="seller_account",
                 target_id=a.id)
    ctx.db.commit()
    return _out(a, conn)
