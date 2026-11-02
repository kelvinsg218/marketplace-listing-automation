"""Mercado Livre official OAuth 2.0 (authorization code + PKCE) and account identification. Nothing here publishes.

Facts from the official documentation (developers.mercadolivre.com.br "Autenticação e autorização" and "Obtenção do
access token"; checked 20/10/2026 for the desktop client and again 02/11/2026):
- authorization: https://auth.mercadolivre.com.br/authorization?response_type=code&client_id&redirect_uri&state
  &code_challenge&code_challenge_method=S256; redirect_uri must be identical to the one registered in the app;
- token: POST https://api.mercadolibre.com/oauth/token (form) grant_type=authorization_code (code, redirect_uri,
  code_verifier) or refresh_token; access token valid 6 h; refresh token single use (each refresh returns a new one
  and only the latest is valid); a refresh token needs the offline_access scope enabled in the app;
- `invalid_grant` = authorization invalid, expired or revoked, or client_id/redirect_uri not matching;
- GET /users/me identifies the account that authorized (id, nickname).
OAuth gives API access only: it does NOT upload the bulk-listing XLSX (that file is still sent by the seller on the
Mercado Livre site). Publishing through the API (POST /items) is a separate, not implemented step (D-036).
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
ME_URL = "https://api.mercadolibre.com/users/me"
TIMEOUT = 25

# transport(method, url, headers, body) -> (status, response bytes); tests inject a fake (no network).
Transport = Callable[[str, str, dict, bytes | None], tuple[int, bytes]]


def _urllib_transport(method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read(2_000_000)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(200_000)


class MLAuthError(RuntimeError):
    """`reauth` = the authorization is gone (invalid_grant): the account must be connected again."""

    def __init__(self, message: str, *, status: int = 0, code: str = "", reauth: bool = False):
        super().__init__(message)
        self.status, self.code, self.reauth = status, code, reauth


@dataclass
class Tokens:
    access_token: str
    refresh_token: str
    expires_in: int
    user_id: str
    scope: str


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]  # 43-128 characters
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class MLOAuthClient:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, transport: Transport | None = None):
        self.client_id, self._secret, self.redirect_uri = client_id, client_secret, redirect_uri
        self._transport = transport or _urllib_transport

    def authorization_url(self, state: str, challenge: str) -> str:
        return AUTH_URL + "?" + urllib.parse.urlencode({
            "response_type": "code", "client_id": self.client_id, "redirect_uri": self.redirect_uri, "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256"})

    def _call(self, method: str, url: str, headers: dict, body: bytes | None) -> dict:
        try:
            status, raw = self._transport(method, url, {"Accept": "application/json", **headers}, body)
        except (OSError, TimeoutError) as exc:
            raise MLAuthError(f"Sem conexão com o Mercado Livre ({type(exc).__name__}).") from None
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            data = {}
        if status == 200:
            return data
        code = str(data.get("error") or "") if isinstance(data, dict) else ""
        message = str((data.get("message") if isinstance(data, dict) else "") or code or f"HTTP {status}")[:300]
        if status == 429:
            message = "O Mercado Livre limitou as requisições; tente novamente em alguns minutos."
        raise MLAuthError(message, status=status, code=code, reauth=code == "invalid_grant")

    def _token(self, form: dict) -> Tokens:
        body = urllib.parse.urlencode({"client_id": self.client_id, "client_secret": self._secret, **form}).encode()
        d = self._call("POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"}, body)
        if not d.get("access_token"):
            raise MLAuthError("Resposta de token sem access_token.")
        return Tokens(d["access_token"], d.get("refresh_token") or "", int(d.get("expires_in") or 0),
                      str(d.get("user_id") or ""), str(d.get("scope") or ""))

    def exchange(self, code: str, verifier: str) -> Tokens:
        return self._token({"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri,
                            "code_verifier": verifier})

    def refresh(self, refresh_token: str) -> Tokens:
        return self._token({"grant_type": "refresh_token", "refresh_token": refresh_token})

    def me(self, access_token: str) -> dict:
        d = self._call("GET", ME_URL, {"Authorization": f"Bearer {access_token}"}, None)
        return {"id": str(d.get("id") or ""), "nickname": str(d.get("nickname") or ""),
                "site_id": str(d.get("site_id") or "")}
