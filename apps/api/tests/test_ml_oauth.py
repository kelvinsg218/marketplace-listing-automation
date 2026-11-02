"""Mercado Livre official OAuth against a FAKE Mercado Livre (no network, no real account, nothing published)."""
from __future__ import annotations

import base64
import json
import os
import urllib.parse
from datetime import timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import select, update

from mla_api.db import utcnow
from mla_api.models import AuditEvent, MarketplaceConnection
from mla_api.services.ml_oauth import AUTH_URL, ME_URL, TOKEN_URL
from mla_api.services.token_crypto import TokenCipher, TokenCryptoError

KEY = base64.b64encode(os.urandom(32)).decode()
REDIRECT = "https://mla.exemplo.com/api/integrations/mercadolivre/callback"


class FakeML:
    """Single-use refresh tokens, like the real one: only the latest refresh token works."""

    def __init__(self, user_id="111", nickname="LOJA_TESTE"):
        self.user_id, self.nickname, self.n = user_id, nickname, 0
        self.access, self.refresh_token, self.fail, self.calls = set(), None, None, []

    def _issue(self):
        self.n += 1
        at, rt = f"APP_USR-at-{self.n}", f"TG-rt-{self.n}"
        self.access.add(at)
        self.refresh_token = rt
        return 200, json.dumps({"access_token": at, "refresh_token": rt, "expires_in": 21600,
                                "user_id": int(self.user_id), "scope": "offline_access read write"}).encode()

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, dict(headers), body))
        if self.fail:
            return self.fail
        if url == TOKEN_URL:
            form = dict(urllib.parse.parse_qsl(body.decode()))
            assert form["client_id"] == "123" and form["client_secret"] == "segredo"
            if form["grant_type"] == "authorization_code":
                assert form["code"] == "TG-code" and form["redirect_uri"] == REDIRECT and len(form["code_verifier"]) >= 43
                return self._issue()
            if form["grant_type"] == "refresh_token" and form["refresh_token"] == self.refresh_token:
                return self._issue()
            return 400, json.dumps({"error": "invalid_grant", "message": "invalid_grant"}).encode()
        if url == ME_URL:
            if headers.get("Authorization", "").removeprefix("Bearer ") not in self.access:
                return 401, json.dumps({"message": "invalid access token"}).encode()
            return 200, json.dumps({"id": int(self.user_id), "nickname": self.nickname, "site_id": "MLB"}).encode()
        return 404, b"{}"


@pytest.fixture
def ml(app):
    fake = FakeML()
    app.state.ml_transport = fake
    app.state.settings = app.state.settings.model_copy(update={
        "ml_client_id": "123", "ml_client_secret": SecretStr("segredo"), "ml_redirect_uri": REDIRECT,
        "token_encryption_key": SecretStr(KEY)})
    return fake


@pytest.fixture
def org(api, ml):
    api.register("dono@example.com", org="Loja")
    o = f"/api/orgs/{api.org_id()}"
    acc = api.post(f"{o}/seller-accounts", json={"label": "Conta principal"}).json()
    return api, o, acc


def connect(api, o, acc_id, code="TG-code", error=""):
    url = api.post(f"{o}/seller-accounts/{acc_id}/oauth/start").json()["authorization_url"]
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    params = {"state": q["state"], **({"code": code} if code else {}), **({"error": error} if error else {})}
    r = api.client.get("/api/integrations/mercadolivre/callback", params=params, follow_redirects=False)
    assert r.status_code == 303
    return r.headers["location"].rsplit("ml=", 1)[1], q


def test_not_configured_says_what_is_missing(api, app):
    api.register("x@example.com", org="X")
    o = f"/api/orgs/{api.org_id()}"
    acc = api.post(f"{o}/seller-accounts", json={"label": "C"}).json()
    st = api.get(f"{o}/integrations/mercadolivre").json()
    assert st["configured"] is False and "MLA_ML_CLIENT_ID" in st["message"] and "MLA_TOKEN_ENCRYPTION_KEY" in st["message"]
    assert api.post(f"{o}/seller-accounts/{acc['id']}/oauth/start").status_code == 409


def test_connect_identifies_account_and_encrypts_tokens(org, app, ml):
    api, o, acc = org
    result, q = connect(api, o, acc["id"])
    assert result == "conectado"
    assert q["response_type"] == "code" and q["client_id"] == "123" and q["redirect_uri"] == REDIRECT
    assert q["code_challenge_method"] == "S256" and len(q["code_challenge"]) == 43
    url = api.post(f"{o}/seller-accounts/{acc['id']}/oauth/start").json()["authorization_url"]
    assert url.startswith(AUTH_URL + "?")
    st = api.get(f"{o}/integrations/mercadolivre").json()
    a = st["accounts"][0]
    assert (a["status"], a["nickname"], a["remote_user_id"], a["external_id"]) == ("connected", "LOJA_TESTE", "111", "111")
    assert "APP_USR" not in json.dumps(st) and "TG-rt" not in json.dumps(st)
    with app.state.sessionmaker() as db:
        conn = db.scalar(select(MarketplaceConnection))
        assert conn.access_token_enc.startswith("v1:") and "APP_USR" not in conn.access_token_enc
        events = db.scalars(select(AuditEvent).where(AuditEvent.action.like("ml.%"))).all()
        assert "ml.connected" in {e.action for e in events}
        assert all("APP_USR" not in json.dumps(e.details) and "TG-" not in json.dumps(e.details) for e in events)


def test_state_is_single_use_and_bound_to_the_user(org, ml, new_api):
    api, o, acc = org
    url = api.post(f"{o}/seller-accounts/{acc['id']}/oauth/start").json()["authorization_url"]
    state = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))["state"]
    other = new_api()
    other.register("intruso@example.com", org="Outra")
    cb = "/api/integrations/mercadolivre/callback"
    r = other.client.get(cb, params={"state": state, "code": "TG-code"}, follow_redirects=False)
    assert r.headers["location"].endswith("ml=sessao")  # not a member of the organization
    assert api.client.get(cb, params={"state": state, "code": "TG-code"},
                          follow_redirects=False).headers["location"].endswith("ml=conectado")
    assert api.client.get(cb, params={"state": state, "code": "TG-code"},
                          follow_redirects=False).headers["location"].endswith("ml=expirado")  # replay
    assert api.client.get(cb, params={"state": "lixo", "code": "x"},
                          follow_redirects=False).headers["location"].endswith("ml=sessao")


def test_denied_and_wrong_account(org, api, ml):
    api_, o, acc = org
    assert connect(api_, o, acc["id"], code="", error="access_denied")[0] == "negado"
    other = api_.post(f"{o}/seller-accounts", json={"label": "Outra", "external_id": "999"}).json()
    assert connect(api_, o, other["id"])[0] == "conta_diferente"  # authorized account 111 != registered 999
    assert connect(api_, o, acc["id"])[0] == "conectado"
    third = api_.post(f"{o}/seller-accounts", json={"label": "Terceira"}).json()
    assert connect(api_, o, third["id"])[0] == "ja_conectada"  # same Mercado Livre account twice


def test_refresh_rotates_single_use_tokens_and_detects_revocation(org, app, ml):
    api, o, acc = org
    connect(api, o, acc["id"])
    base = f"{o}/seller-accounts/{acc['id']}/oauth"
    assert api.post(f"{base}/refresh").json()["status"] == "connected"
    assert ml.refresh_token == "TG-rt-2"
    # Near expiry: the check renews first, with the latest refresh token.
    with app.state.sessionmaker() as db:
        db.execute(update(MarketplaceConnection).values(expires_at=utcnow() + timedelta(minutes=1)))
        db.commit()
    assert api.post(f"{base}/check").json()["status"] == "connected" and ml.refresh_token == "TG-rt-3"
    # Revoked on the Mercado Livre side: the refresh token stops working -> reconnect needed, tokens erased.
    ml.refresh_token = "revogado"
    r = api.post(f"{base}/refresh")
    assert r.status_code == 409 and "conecte a conta novamente" in r.json()["detail"]
    a = api.get(f"{o}/integrations/mercadolivre").json()["accounts"][0]
    assert a["status"] == "needs_reauth"
    with app.state.sessionmaker() as db:
        conn = db.scalar(select(MarketplaceConnection))
        assert conn.access_token_enc == "" and conn.refresh_token_enc == ""
    assert "ml.reauth_needed" in [e["action"] for e in api.get(f"{o}/audit").json()]


def test_transient_failure_keeps_tokens(org, ml):
    api, o, acc = org
    connect(api, o, acc["id"])
    ml.fail = (429, b"{}")
    r = api.post(f"{o}/seller-accounts/{acc['id']}/oauth/check")
    assert r.status_code == 502 and "limitou" in r.json()["detail"]
    a = api.get(f"{o}/integrations/mercadolivre").json()["accounts"][0]
    assert a["status"] == "error"
    ml.fail = None
    assert api.post(f"{o}/seller-accounts/{acc['id']}/oauth/check").json()["status"] == "connected"


def test_disconnect_erases_tokens(org, app, ml):
    api, o, acc = org
    connect(api, o, acc["id"])
    assert api.post(f"{o}/seller-accounts/{acc['id']}/oauth/disconnect").json()["status"] == "disconnected"
    with app.state.sessionmaker() as db:
        assert db.scalar(select(MarketplaceConnection)).access_token_enc == ""
    assert api.post(f"{o}/seller-accounts/{acc['id']}/oauth/check").status_code == 409


def test_isolation_and_roles(org, ml, new_api):
    api, o, acc = org
    connect(api, o, acc["id"])
    other = new_api()
    other.register("b@example.com", org="B")
    ob = f"/api/orgs/{other.org_id()}"
    for path in ("start", "check", "refresh", "disconnect"):
        assert other.post(f"{ob}/seller-accounts/{acc['id']}/oauth/{path}").status_code == 404
    assert other.get(f"{ob}/integrations/mercadolivre").json()["accounts"] == []


def test_token_cipher_binds_row():
    c = TokenCipher(KEY)
    enc = c.encrypt("APP_USR-x", "org:acc:access")
    assert c.decrypt(enc, "org:acc:access") == "APP_USR-x"
    with pytest.raises(TokenCryptoError):
        c.decrypt(enc, "outra-org:acc:access")
    with pytest.raises(TokenCryptoError):
        TokenCipher(base64.b64encode(os.urandom(32)).decode()).decrypt(enc, "org:acc:access")
    with pytest.raises(TokenCryptoError, match="32 bytes"):
        TokenCipher(base64.b64encode(b"curta").decode())
