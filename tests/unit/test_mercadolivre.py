"""Mercado Livre official API integration against a local fake of the documented endpoints.

The fake follows developers.mercadolivre.com.br: PKCE check on /oauth/token, single-use refresh tokens,
/users/me, public category endpoints, POST /items/validate (204 valid / 400 with causes), seller items search,
/items/bulk and descriptions. No real account is touched.
"""
import base64
import hashlib
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import make_png

from mla.core.enums import Marketplace
from mla.integrations.mercadolivre import (
    MercadoLivreAPI, MLApiError, MLNotConnected, MercadoLivreService, parse_redirect,
)

ATTRIBUTES = [
    {"id": "BRAND", "name": "Marca", "tags": {"required": True, "catalog_required": True}},
    {"id": "MODEL", "name": "Modelo", "tags": {}},
    {"id": "PART_NUMBER", "name": "Número de peça", "tags": {"required": True}},
    {"id": "UNITS_PER_PACK", "name": "Quantidade de filtros por pacote", "tags": {"conditional_required": True}},
    {"id": "GTIN", "name": "GTIN", "tags": {"conditional_required": True}},
    {"id": "SELLER_SKU", "name": "SKU", "tags": {}},
    {"id": "ITEM_CONDITION", "name": "Condição", "tags": {"read_only": True, "required": True}},
]


PNG = b""


class FakeML:
    def __init__(self):
        self.challenge = ""
        self.access = ""
        self.refresh = ""
        self.counter = 0
        self.validated = []
        self.calls = []

    def tokens(self):
        self.counter += 1
        self.access, self.refresh = f"APP_USR-{self.counter}", f"TG-refresh-{self.counter}"
        return {"access_token": self.access, "token_type": "bearer", "expires_in": 21600,
                "scope": "offline_access read write", "user_id": 123, "refresh_token": self.refresh}


@pytest.fixture
def fake(tmp_path):
    global PNG
    PNG = make_png(tmp_path / "foto.png", 600, 600).read_bytes()
    state = FakeML()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, code, body=None, raw: bytes | None = None):
            data = raw if raw is not None else (b"" if body is None else json.dumps(body).encode())
            self.send_response(code)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def authed(self):
            return self.headers.get("Authorization") == f"Bearer {state.access}"

        def do_GET(self):
            state.calls.append(("GET", self.path))
            path = urllib.parse.urlsplit(self.path).path
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            if path == "/authorization":
                state.challenge = query["code_challenge"][0]
                return self.reply(200, {})
            if path.startswith("/sites/MLB/domain_discovery/search"):
                return self.reply(200, [{"domain_id": "MLB-VEHICLE_OIL_FILTERS", "domain_name": "Filtros de óleo",
                                         "category_id": "MLB47120", "category_name": "Filtros de Óleo"}])
            if path == "/categories/MLB47120/attributes":
                return self.reply(200, ATTRIBUTES)
            if path == "/pic/1.jpg":
                return self.reply(200, raw=PNG)
            if not self.authed():
                return self.reply(401, {"message": "invalid access token", "error": "not_found", "status": 401})
            if path == "/users/me":
                return self.reply(200, {"id": 123, "nickname": "LOJA_TESTE", "site_id": "MLB"})
            if path == "/sites/MLB/listing_types":
                return self.reply(200, [{"id": "gold_special", "name": "Clássico"}, {"id": "gold_pro", "name": "Premium"}])
            if path == "/users/123/items/search":
                return self.reply(200, {"results": ["MLB1", "MLB2"], "paging": {"total": 2, "offset": 0, "limit": 50}})
            if path == "/items/bulk":
                base = f"http://127.0.0.1:{server.server_port}"
                items = {
                    "MLB1": {"id": "MLB1", "title": "Filtro de óleo Aurora", "price": 29.9, "available_quantity": 5,
                             "condition": "new", "permalink": "https://produto/MLB1",
                             "attributes": [{"id": "SELLER_SKU", "value_name": "AUR-1"},
                                            {"id": "BRAND", "value_name": "Aurora"}],
                             "pictures": [{"secure_url": f"{base}/pic/1.jpg"}], "variations": []},
                    "MLB2": {"id": "MLB2", "title": "Tapete", "price": 99.0, "available_quantity": 0,
                             "condition": "used", "attributes": [], "pictures": [],
                             "variations": [{"id": 77, "price": 99.0, "available_quantity": 3,
                                             "attribute_combinations": [{"name": "Cor", "value_name": "Preto"}],
                                             "attributes": [{"id": "SELLER_SKU", "value_name": "TAP-PT"}]}]},
                }
                ids = query["ids"][0].split(",")
                return self.reply(200, [{"code": 200, "body": items[i]} for i in ids])
            if path.endswith("/description"):
                return self.reply(200, {"plain_text": "Descrição do vendedor."})
            return self.reply(404, {"message": "not found"})

        def do_POST(self):
            state.calls.append(("POST", self.path))
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode()
            if self.path == "/oauth/token":
                form = {k: v[0] for k, v in urllib.parse.parse_qs(body).items()}
                if form["grant_type"] == "authorization_code":
                    digest = hashlib.sha256(form["code_verifier"].encode()).digest()
                    ok = form["code"] == "TG-codigo" and \
                        base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == state.challenge
                    return self.reply(200, state.tokens()) if ok else self.reply(400, {"error": "invalid_grant"})
                if form["grant_type"] == "refresh_token":
                    if form["refresh_token"] != state.refresh:  # single use
                        return self.reply(400, {"error": "invalid_grant", "message": "invalid_grant"})
                    return self.reply(200, state.tokens())
            if self.path == "/items/validate":
                if not self.authed():
                    return self.reply(401, {"message": "unauthorized"})
                item = json.loads(body)
                state.validated.append(item)
                ids = {a["id"] for a in item.get("attributes", [])}
                if "PART_NUMBER" not in ids:
                    return self.reply(400, {"message": "Validation error", "error": "validation_error", "status": 400,
                                            "cause": [{"type": "error", "code": "item.attributes.missing_required",
                                                       "message": "The attributes [PART_NUMBER] are required"}]})
                return self.reply(204)
            return self.reply(404, {"message": "not found"})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state.base = f"http://127.0.0.1:{server.server_port}"
    yield state
    server.shutdown()


@pytest.fixture
def ml(ctx, fake):
    ctx.mercadolivre = MercadoLivreService(ctx.db, ctx.accounts, MercadoLivreAPI(fake.base, fake.base, timeout=10))
    return ctx.mercadolivre


@pytest.fixture
def account(ctx):
    return ctx.accounts.default_for(Marketplace.MERCADO_LIVRE)


def _connect(ml, fake, account):
    url = ml.start_connect(account.id, "1234567890", "segredo-do-app", "https://localhost.com/redirect")
    urllib.request.urlopen(url.replace("https://auth.mercadolivre.com.br", fake.base))  # browser step
    state = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["state"][0]
    return ml.finish_connect(account.id, f"https://localhost.com/redirect?code=TG-codigo&state={state}")


import urllib.request  # noqa: E402


def test_connect_with_pkce_stores_tokens_encrypted(ml, fake, account, ctx):
    connection = _connect(ml, fake, account)
    assert connection.nickname == "LOJA_TESTE" and connection.remote_user_id == "123" and connection.connected
    row = ctx.db.query_one("SELECT * FROM marketplace_api_credentials WHERE account_id = ?", (account.id,))
    for column in ("client_secret_enc", "access_token_enc", "refresh_token_enc"):
        assert b"segredo" not in row[column] and b"APP_USR" not in row[column] and b"TG-" not in row[column]
    assert ml.check(account.id).nickname == "LOJA_TESTE"


def test_wrong_state_or_garbage_is_refused(ml, fake, account):
    ml.start_connect(account.id, "1234567890", "s", "https://localhost.com/redirect")
    with pytest.raises(MLApiError, match="não corresponde"):
        ml.finish_connect(account.id, "https://localhost.com/redirect?code=TG-codigo&state=outro")
    with pytest.raises(MLApiError, match="endereço completo"):
        parse_redirect("qualquer coisa")
    with pytest.raises(MLApiError, match="recusou"):
        parse_redirect("https://localhost.com/redirect?error=access_denied&error_description=negado")


def test_invalid_app_settings_are_explained(ml, account):
    with pytest.raises(MLApiError, match="numérico"):
        ml.start_connect(account.id, "abc", "s", "https://x.com/r")
    with pytest.raises(MLApiError, match="HTTPS"):
        ml.start_connect(account.id, "123", "s", "http://localhost:8080/cb")


def test_expired_token_is_refreshed_once_and_rotation_is_saved(ml, fake, account, ctx):
    _connect(ml, fake, account)
    ctx.db.execute("UPDATE marketplace_api_credentials SET expires_at = '2000-01-01T00:00:00+00:00'")
    assert ml.access_token(account.id) == "APP_USR-2"            # refreshed
    assert ml.access_token(account.id) == "APP_USR-2"            # still valid: no new refresh
    ctx.db.execute("UPDATE marketplace_api_credentials SET expires_at = '2000-01-01T00:00:00+00:00'")
    fake.refresh = "TG-outro"                                     # revoked elsewhere
    with pytest.raises(MLNotConnected):
        ml.access_token(account.id)
    assert "conecte de novo" in ml.connection(account.id).last_error


def test_not_connected_is_reported(ml, account):
    with pytest.raises(MLNotConnected):
        ml.access_token(account.id)


def test_category_tools_are_public(ml):
    assert ml.suggest_categories("Filtro de óleo Aurora")[0]["category_id"] == "MLB47120"
    required = {a["id"]: a["_kind"] for a in ml.required(ml.category_attributes("MLB47120"))}
    assert required == {"BRAND": "obrigatório", "PART_NUMBER": "obrigatório", "UNITS_PER_PACK": "condicional",
                        "GTIN": "condicional"}  # read-only ITEM_CONDITION is not asked from the user
    with pytest.raises(MLApiError):
        ml.category_attributes("123; DROP")


def test_validate_listing_without_publishing(ctx, ml, fake, account, complete_product):
    _connect(ml, fake, account)
    product = complete_product("VAL-1", brand="Aurora", gtin="7891234567890")  # invalid check digit
    ctx.catalog.save(product)
    listing = ctx.listings.get(ctx.listings.prepare([product.id], Marketplace.MERCADO_LIVRE, account.id).created[0])
    listing.category_id, listing.listing_type = "MLB47120", "Clássico"
    listing.attributes = {"Número de peça": "AX-1", "Cor inventada": "azul"}
    ctx.listings.save(listing)
    payload = ctx.listings.payload(ctx.listings.get(listing.id))
    outcome = ml.validate_listing(account.id, product, payload)
    assert outcome.valid
    sent = {a["id"]: a["value_name"] for a in outcome.sent["attributes"]}
    assert sent["PART_NUMBER"] == "AX-1" and sent["BRAND"] == "Aurora" and sent["SELLER_SKU"] == "VAL-1"
    assert "GTIN" not in sent                                       # invalid GTIN never sent
    assert outcome.sent["listing_type_id"] == "gold_special" and outcome.sent["price"] == 129.9
    assert any("Cor inventada" in m for _, m in outcome.local)
    assert not any(c[1].startswith("/items") and c[0] == "POST" and c[1] != "/items/validate" for c in fake.calls)
    listing.attributes = {}
    ctx.listings.save(listing)
    outcome = ml.validate_listing(account.id, product, ctx.listings.payload(ctx.listings.get(listing.id)))
    assert not outcome.valid and "PART_NUMBER" in outcome.problems[0][1]
    assert any("Número de peça" in m for s, m in outcome.local if s == "error")


def test_import_seller_listings_goes_through_the_import_center(ctx, ml, fake, account, tmp_path):
    _connect(ml, fake, account)
    path = ml.export_seller_listings(account.id, tmp_path / "ml")
    records = json.loads(path.read_text(encoding="utf-8"))
    assert [r["sku"] for r in records] == ["AUR-1", "ML-MLB2", "TAP-PT"]
    assert records[0]["imagens"] == "fotos/AUR-1-01.png" and (tmp_path / "ml" / "fotos" / "AUR-1-01.png").exists()
    analysis = ctx.imports.analyze(path)
    batch = ctx.imports.plan(analysis, analysis.mapping())
    ctx.imports.commit(batch.id)
    product = ctx.catalog.get(ctx.products.id_for_sku("AUR-1"))
    assert (product.price_cents, product.stock, product.brand, len(product.images)) == (2990, 5, "Aurora", 1)
    assert "MLB1" in product.internal_notes
    tapete = ctx.catalog.get(ctx.products.id_for_sku("ML-MLB2"))
    assert [(v.sku, v.stock) for v in tapete.variants] == [("TAP-PT", 3)]
