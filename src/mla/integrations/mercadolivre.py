"""Mercado Livre official API: OAuth (authorization code + PKCE), category tools, listing validation without
publishing and import of the seller's existing listings.

Facts checked in the official documentation (developers.mercadolivre.com.br, 20/10/2026):
- authorization: https://auth.mercadolivre.com.br/authorization?response_type=code&client_id&redirect_uri
  &code_challenge&code_challenge_method (PKCE) [&state]; redirect_uri must match the app settings exactly;
- token: POST https://api.mercadolibre.com/oauth/token (form) grant_type=authorization_code|refresh_token;
  access token 6 h; refresh token 6 months and single use (each refresh returns a new one);
- POST /items/validate validates a listing without creating it (204 = valid); there is no sandbox;
- /users/{id}/items/search lists the seller's items; /items/bulk?ids= (max 20) replaces /items?ids=;
- /sites/MLB/domain_discovery/search and /categories/{id}/attributes are public.
Publishing (POST /items) is deliberately NOT implemented here: it needs the owner's explicit authorization.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
import threading
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from mla.core.enums import Marketplace
from mla.core.validation import gtin_valid
from mla.integrations import secure_store
from mla.persistence.db import Database, now_iso

log = logging.getLogger(__name__)

API_BASE = "https://api.mercadolibre.com"
AUTH_BASE = "https://auth.mercadolivre.com.br"
SITE = "MLB"
PROVIDER = "mercadolivre"


class MLApiError(RuntimeError):
    def __init__(self, message: str, status: int = 0, causes: list[dict] | None = None):
        super().__init__(message)
        self.status = status
        self.causes = causes or []


class MLNotConnected(MLApiError):
    pass


class MLCancelled(MLApiError):
    pass


def _allowed(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost"))


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


# ============================================================================ HTTP client
class MercadoLivreAPI:
    def __init__(self, api_base: str = API_BASE, auth_base: str = AUTH_BASE, timeout: float = 25):
        self.api_base = api_base.rstrip("/")
        self.auth_base = auth_base.rstrip("/")
        self.timeout = timeout

    def authorization_url(self, client_id: str, redirect_uri: str, state: str, challenge: str) -> str:
        query = urllib.parse.urlencode({"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri,
                                        "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})
        return f"{self.auth_base}/authorization?{query}"

    def request(self, method: str, path: str, token: str | None = None, body=None, form: dict | None = None,
                raw: bool = False):
        url = path if path.startswith("http") else f"{self.api_base}{path}"
        if not _allowed(url):
            raise MLApiError(f"Endereço recusado (só HTTPS): {url}")
        headers = {"Accept": "application/json", "User-Agent": "MLA-desktop"}
        data = None
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310 (checked)
                payload = response.read(30 * 1024 * 1024)
                if raw:
                    return payload
                return json.loads(payload) if payload.strip() else None
        except urllib.error.HTTPError as exc:
            text = exc.read(200_000).decode("utf-8", "replace")
            try:
                detail = json.loads(text)
            except ValueError:
                detail = {"message": text[:300]}
            message = detail.get("message") or detail.get("error") or f"HTTP {exc.code}"
            if exc.code == 429:
                message = "O Mercado Livre limitou as consultas (muitas requisições). Aguarde alguns minutos."
            raise MLApiError(str(message), exc.code, detail.get("cause") or []) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise MLApiError(f"Sem conexão com o Mercado Livre ({exc}).") from None


# ============================================================================ connection storage
@dataclass
class MLConnection:
    account_id: int
    client_id: str
    redirect_uri: str
    remote_user_id: str = ""
    nickname: str = ""
    expires_at: str = ""
    connected_at: str = ""
    checked_at: str = ""
    last_error: str = ""
    has_tokens: bool = False

    @property
    def connected(self) -> bool:
        return self.has_tokens and not self.last_error


@dataclass
class _Pending:
    state: str
    verifier: str
    client_id: str
    client_secret: str
    redirect_uri: str


@dataclass
class ValidationOutcome:
    valid: bool
    problems: list[tuple[str, str]] = field(default_factory=list)   # (severity, message) from Mercado Livre
    local: list[tuple[str, str]] = field(default_factory=list)      # MLA notes about what was (not) sent
    sent: dict = field(default_factory=dict)


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def parse_redirect(text: str) -> tuple[str, str]:
    """(code, state) from the final address the browser showed, or a bare code."""
    text = (text or "").strip()
    if "error=" in text and "code=" not in text:
        query = urllib.parse.parse_qs(urlsplit(text).query or text.split("?", 1)[-1])
        reason = (query.get("error_description") or query.get("error") or ["sem detalhe"])[0]
        raise MLApiError(f"O Mercado Livre recusou a autorização: {reason}")
    if "code=" in text:
        query = urllib.parse.parse_qs(urlsplit(text).query or text.split("?", 1)[-1])
        if "error" in query:
            raise MLApiError(f"O Mercado Livre recusou a autorização: {query.get('error_description', query['error'])[0]}")
        return (query.get("code") or [""])[0].strip(), (query.get("state") or [""])[0].strip()
    if re.fullmatch(r"TG-[A-Za-z0-9\-]+", text):
        return text, ""
    raise MLApiError("Cole o endereço completo que apareceu no navegador depois de autorizar (ele contém code=…).")


class MercadoLivreService:
    def __init__(self, db: Database, accounts, api: MercadoLivreAPI | None = None):
        self.db = db
        self.accounts = accounts
        self.api = api or MercadoLivreAPI()
        self._pending: dict[int, _Pending] = {}
        self._lock = threading.Lock()  # refresh tokens are single use: never refresh twice at once
        self._listing_types: dict[int, list[dict]] = {}

    # ------------------------------------------------------------------ connection
    def connection(self, account_id: int) -> MLConnection | None:
        row = self.db.query_one("SELECT * FROM marketplace_api_credentials WHERE account_id = ? AND provider = ?",
                                (account_id, PROVIDER))
        if row is None:
            return None
        return MLConnection(account_id, row["client_id"], row["redirect_uri"], row["remote_user_id"], row["nickname"],
                            row["expires_at"] or "", row["connected_at"] or "", row["checked_at"] or "",
                            row["last_error"], row["refresh_token_enc"] is not None)

    def _account(self, account_id: int):
        account = self.accounts.get(account_id)
        if account is None or account.marketplace is not Marketplace.MERCADO_LIVRE:
            raise MLApiError("Conta do Mercado Livre não encontrada.")
        return account

    def start_connect(self, account_id: int, client_id: str, client_secret: str, redirect_uri: str) -> str:
        self._account(account_id)
        client_id, client_secret, redirect_uri = client_id.strip(), client_secret.strip(), redirect_uri.strip()
        if not client_id.isdigit():
            raise MLApiError("O App ID (client_id) do Mercado Livre é numérico; copie-o do seu aplicativo.")
        if not client_secret:
            raise MLApiError("Informe a Secret Key do seu aplicativo.")
        if not redirect_uri.startswith("https://") or "?" in redirect_uri:
            raise MLApiError("Use a URI de redirecionamento HTTPS exatamente como cadastrada no aplicativo, sem "
                             "parâmetros (o Mercado Livre exige que seja idêntica).")
        verifier, challenge = _pkce()
        state = secrets.token_urlsafe(24)
        self._pending[account_id] = _Pending(state, verifier, client_id, client_secret, redirect_uri)
        return self.api.authorization_url(client_id, redirect_uri, state, challenge)

    def finish_connect(self, account_id: int, pasted: str) -> MLConnection:
        pending = self._pending.get(account_id)
        if pending is None:
            raise MLApiError("Clique primeiro em Abrir autorização (a sessão de autorização expirou).")
        code, state = parse_redirect(pasted)
        if state and state != pending.state:
            raise MLApiError("Este endereço não corresponde à autorização aberta agora; abra a autorização de novo.")
        tokens = self.api.request("POST", "/oauth/token", form={
            "grant_type": "authorization_code", "client_id": pending.client_id, "client_secret": pending.client_secret,
            "code": code, "redirect_uri": pending.redirect_uri, "code_verifier": pending.verifier})
        me = self.api.request("GET", "/users/me", token=tokens["access_token"])
        now = now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO marketplace_api_credentials (account_id, provider, client_id, client_secret_enc, "
                "redirect_uri, access_token_enc, refresh_token_enc, expires_at, remote_user_id, nickname, "
                "connected_at, checked_at, last_error, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?) "
                "ON CONFLICT(account_id) DO UPDATE SET provider = excluded.provider, client_id = excluded.client_id, "
                "client_secret_enc = excluded.client_secret_enc, redirect_uri = excluded.redirect_uri, "
                "access_token_enc = excluded.access_token_enc, refresh_token_enc = excluded.refresh_token_enc, "
                "expires_at = excluded.expires_at, remote_user_id = excluded.remote_user_id, "
                "nickname = excluded.nickname, connected_at = excluded.connected_at, "
                "checked_at = excluded.checked_at, last_error = '', updated_at = excluded.updated_at",
                (account_id, PROVIDER, pending.client_id, secure_store.protect(pending.client_secret),
                 pending.redirect_uri, secure_store.protect(tokens["access_token"]),
                 secure_store.protect(tokens["refresh_token"]), _expiry(tokens), str(me.get("id", "")),
                 me.get("nickname", ""), now, now, now))
        self._pending.pop(account_id, None)
        log.info("conta %s conectada à API do Mercado Livre como %s", account_id, me.get("nickname"))
        return self.connection(account_id)

    def disconnect(self, account_id: int) -> None:
        self.db.execute("DELETE FROM marketplace_api_credentials WHERE account_id = ?", (account_id,))
        self._listing_types.pop(account_id, None)

    def access_token(self, account_id: int) -> str:
        with self._lock:
            row = self.db.query_one("SELECT * FROM marketplace_api_credentials WHERE account_id = ?", (account_id,))
            if row is None or row["refresh_token_enc"] is None:
                raise MLNotConnected("Conta não conectada à API oficial do Mercado Livre.")
            expires = datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None
            if expires is not None and expires - datetime.now(timezone.utc) > timedelta(minutes=5):
                return secure_store.unprotect(row["access_token_enc"])
            try:
                tokens = self.api.request("POST", "/oauth/token", form={
                    "grant_type": "refresh_token", "client_id": row["client_id"],
                    "client_secret": secure_store.unprotect(row["client_secret_enc"]),
                    "refresh_token": secure_store.unprotect(row["refresh_token_enc"])})
            except MLApiError as exc:
                if exc.status in (400, 401):
                    self.db.execute("UPDATE marketplace_api_credentials SET last_error = ?, updated_at = ? "
                                    "WHERE account_id = ?", ("Autorização expirada ou revogada; conecte de novo.",
                                                             now_iso(), account_id))
                    raise MLNotConnected("A autorização expirou ou foi revogada; conecte a conta de novo.") from exc
                raise
            self.db.execute(
                "UPDATE marketplace_api_credentials SET access_token_enc = ?, refresh_token_enc = ?, expires_at = ?, "
                "last_error = '', updated_at = ? WHERE account_id = ?",
                (secure_store.protect(tokens["access_token"]), secure_store.protect(tokens["refresh_token"]),
                 _expiry(tokens), now_iso(), account_id))
            return tokens["access_token"]

    def check(self, account_id: int) -> MLConnection:
        """Real check: /users/me with the stored (refreshed if needed) token."""
        me = self.api.request("GET", "/users/me", token=self.access_token(account_id))
        self.db.execute("UPDATE marketplace_api_credentials SET remote_user_id = ?, nickname = ?, checked_at = ?, "
                        "last_error = '', updated_at = ? WHERE account_id = ?",
                        (str(me.get("id", "")), me.get("nickname", ""), now_iso(), now_iso(), account_id))
        return self.connection(account_id)

    # ------------------------------------------------------------------ categories (public)
    def suggest_categories(self, title: str, limit: int = 4) -> list[dict]:
        if len((title or "").strip()) < 3:
            raise MLApiError("Escreva o título do anúncio para sugerir a categoria.")
        query = urllib.parse.urlencode({"limit": limit, "q": title.strip()})
        found = self.api.request("GET", f"/sites/{SITE}/domain_discovery/search?{query}") or []
        return [{"category_id": f.get("category_id", ""), "category_name": f.get("category_name", ""),
                 "domain_name": f.get("domain_name", "")} for f in found if f.get("category_id")]

    def category_attributes(self, category_id: str) -> list[dict]:
        if not re.fullmatch(rf"{SITE}\d+", category_id or ""):
            raise MLApiError(f"ID de categoria do Mercado Livre inválido: {category_id!r} (ex.: {SITE}47120).")
        return self.api.request("GET", f"/categories/{category_id}/attributes") or []

    @staticmethod
    def required(attributes: list[dict]) -> list[dict]:
        result = []
        for a in attributes:
            tags = a.get("tags") or {}
            if tags.get("read_only"):
                continue
            if tags.get("required") or tags.get("catalog_required"):
                result.append({**a, "_kind": "obrigatório"})
            elif tags.get("conditional_required"):
                result.append({**a, "_kind": "condicional"})
        return result

    # ------------------------------------------------------------------ listings
    def listing_types(self, account_id: int) -> list[dict]:
        if account_id not in self._listing_types:
            types = self.api.request("GET", f"/sites/{SITE}/listing_types", token=self.access_token(account_id))
            self._listing_types[account_id] = types or []
        return self._listing_types[account_id]

    def build_item(self, product, payload, attributes: list[dict], listing_types: list[dict]
                   ) -> tuple[dict, list[tuple[str, str]]]:
        """Mercado Livre item JSON from the effective listing content. Never invents values."""
        notes: list[tuple[str, str]] = []
        by_id = {a["id"]: a for a in attributes}
        by_name = {_fold(a.get("name", "")): a["id"] for a in attributes}
        values: dict[str, str] = {}
        if product.brand:
            values["BRAND"] = product.brand
        if product.model:
            values["MODEL"] = product.model
        if product.sku:
            values["SELLER_SKU"] = product.sku
        if product.gtin:
            if gtin_valid(product.gtin):
                values["GTIN"] = product.gtin
            else:
                notes.append(("error", f"GTIN {product.gtin} inválido não foi enviado."))
        for name, value in (payload.attributes or {}).items():
            if not str(value).strip():
                continue
            key = name.strip()
            attr_id = key if re.fullmatch(r"[A-Z0-9_]+", key) and (key in by_id or not by_id) else by_name.get(_fold(key))
            if attr_id is None:
                notes.append(("warning", f"Atributo \"{name}\" não existe nesta categoria; não foi enviado."))
                continue
            values[attr_id] = str(value).strip()
        condition = {"new": "new", "used": "used"}.get(product.condition.value)
        if condition is None:
            notes.append(("warning", "Condição \"recondicionado\" não tem correspondência direta; revise e envie "
                                     "como atributo da categoria, se existir."))
        wanted = _fold(payload.listing_type or "classico")
        type_id = next((t.get("id") for t in listing_types if _fold(t.get("name", "")) == wanted), None)
        if type_id is None:
            notes.append(("warning", f"Tipo de anúncio \"{payload.listing_type or 'Clássico'}\" não encontrado na "
                                     "conta; enviado sem tipo."))
        item = {"title": payload.title, "category_id": payload.category_id,
                "price": round((payload.price_cents or 0) / 100, 2), "currency_id": "BRL",
                "available_quantity": int(payload.stock or 0), "buying_mode": "buy_it_now",
                "description": {"plain_text": payload.description},
                "attributes": [{"id": k, "value_name": v} for k, v in values.items()]}
        if condition:
            item["condition"] = condition
        if type_id:
            item["listing_type_id"] = type_id
        if payload.images:
            notes.append(("info", f"{len(payload.images)} foto(s) do MLA não foram enviadas: o validador exige links "
                                  "públicos; as fotos serão enviadas só na publicação autorizada."))
        if product.variants:
            notes.append(("warning", f"{len(product.variants)} variação(ões) ainda não são enviadas nesta validação."))
        for attr in self.required(attributes):
            if attr["_kind"] == "obrigatório" and attr["id"] not in values:
                notes.append(("error", f"Falta o atributo obrigatório \"{attr.get('name', attr['id'])}\" "
                                       f"({attr['id']})."))
        return item, notes

    def validate_listing(self, account_id: int, product, payload) -> ValidationOutcome:
        """POST /items/validate: checks the listing on Mercado Livre WITHOUT creating it."""
        attributes = self.category_attributes(payload.category_id)
        item, notes = self.build_item(product, payload, attributes, self.listing_types(account_id))
        try:
            self.api.request("POST", "/items/validate", token=self.access_token(account_id), body=item)
        except MLApiError as exc:
            if exc.status != 400:
                raise
            problems = [("error" if c.get("type") != "warning" else "warning",
                         c.get("message") or c.get("code") or "") for c in exc.causes] or [("error", str(exc))]
            return ValidationOutcome(False, problems, notes, item)
        return ValidationOutcome(True, [], notes, item)

    # ------------------------------------------------------------------ import of existing listings
    def export_seller_listings(self, account_id: int, folder: Path,
                               progress: Callable[[int, int, str], None] | None = None,
                               cancel: threading.Event | None = None, limit: int = 1000) -> Path:
        """Write the seller's listings as a JSON file (+ photos) for the import center. Read only."""
        progress = progress or (lambda *_: None)
        conn = self.connection(account_id)
        if conn is None or not conn.has_tokens:
            raise MLNotConnected("Conecte a conta à API oficial antes de importar os anúncios.")
        token = self.access_token(account_id)
        user_id = conn.remote_user_id or str(self.api.request("GET", "/users/me", token=token)["id"])
        ids: list[str] = []
        offset = 0
        while len(ids) < limit:
            page = self.api.request("GET", f"/users/{user_id}/items/search?offset={offset}&limit=50", token=token)
            results = page.get("results") or []
            ids += results
            total = int((page.get("paging") or {}).get("total") or 0)
            progress(len(ids), min(total, limit), "Listando anúncios da conta")
            offset += 50
            if not results or offset >= total or (cancel is not None and cancel.is_set()):
                break
        ids = ids[:limit]
        folder.mkdir(parents=True, exist_ok=True)
        photos = folder / "fotos"
        photos.mkdir(exist_ok=True)
        records: list[dict] = []
        for start in range(0, len(ids), 20):
            if cancel is not None and cancel.is_set():
                raise MLCancelled("Importação cancelada.")
            batch = self.api.request("GET", f"/items/bulk?ids={','.join(ids[start:start + 20])}",
                                     token=self.access_token(account_id)) or []
            for entry in batch:
                body = entry.get("body") if isinstance(entry, dict) and "body" in entry else entry
                if not isinstance(body, dict) or entry.get("code", 200) != 200:
                    continue
                records += self._records(body, account_id, photos)
            progress(min(start + 20, len(ids)), len(ids), "Lendo anúncios e fotos")
        target = folder / "anuncios-mercado-livre.json"
        target.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
        log.info("conta %s: %s anúncio(s) do Mercado Livre exportados para importação", account_id, len(ids))
        return target

    def _records(self, item: dict, account_id: int, photos: Path) -> list[dict]:
        attrs = {a.get("id"): a.get("value_name") or "" for a in item.get("attributes") or []}
        sku = attrs.get("SELLER_SKU") or item.get("seller_custom_field") or f"ML-{item.get('id')}"
        try:
            description = (self.api.request("GET", f"/items/{item['id']}/description",
                                            token=self.access_token(account_id)) or {}).get("plain_text", "")
        except MLApiError:
            description = ""
        files = []
        for n, picture in enumerate((item.get("pictures") or [])[:12], start=1):
            url = picture.get("secure_url") or picture.get("url") or ""
            if not _allowed(url):
                continue
            try:
                data = self.api.request("GET", url, raw=True)
            except MLApiError:
                continue
            extension = _image_extension(data)
            if extension is None:
                continue  # not an image: never written to disk
            name = f"{_safe_name(sku)}-{n:02d}{extension}"
            (photos / name).write_bytes(data)
            files.append(f"fotos/{name}")
        price = item.get("price")
        base = {
            "sku": sku, "nome": item.get("title", ""), "titulo": item.get("title", ""),
            "descricao_completa": description, "preco": f"{price:.2f}".replace(".", ",") if price else "",
            "estoque": str(item.get("available_quantity", "")), "marca": attrs.get("BRAND", ""),
            "modelo": attrs.get("MODEL", ""), "ean": attrs.get("GTIN", ""),
            "condicao": {"new": "novo", "used": "usado"}.get(item.get("condition", ""), ""),
            "imagens": " | ".join(files),
            "observacoes": f"Importado do Mercado Livre: {item.get('id')} {item.get('permalink', '')}".strip(),
        }
        records = [base]
        for variation in item.get("variations") or []:
            vattrs = {a.get("id"): a.get("value_name") or "" for a in variation.get("attributes") or []}
            combo = ", ".join(f"{c.get('name')}: {c.get('value_name')}" for c in variation.get("attribute_combinations")
                              or [])
            records.append({"sku": vattrs.get("SELLER_SKU") or variation.get("seller_custom_field")
                            or f"{sku}-{variation.get('id')}", "sku_pai": sku, "variacao": combo or "Variação",
                            "preco": f"{variation['price']:.2f}".replace(".", ",") if variation.get("price") else "",
                            "estoque": str(variation.get("available_quantity", ""))})
        return records


def _expiry(tokens: dict) -> str:
    seconds = int(tokens.get("expires_in") or 21600)
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(timespec="seconds")


def _image_extension(data: bytes) -> str | None:
    if data[:3] == bytes([0xFF, 0xD8, 0xFF]):
        return ".jpg"
    if data[:8] == bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]):
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def _safe_name(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text)[:60] or "item"
