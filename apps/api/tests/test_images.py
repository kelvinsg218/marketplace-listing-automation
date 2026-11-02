"""Central de Imagens and Estúdio de IA. The AI provider here is a TEST DOUBLE (it inverts bytes of a PNG we build);
no real provider exists in the product and none is simulated there."""
from __future__ import annotations

import socket

import pytest
from helpers import make_png

from mla_api.services import safe_fetch

URL = "https://http2.mlstatic.com/D_NQ_NP_000000-MLA00000000000_000000-F.jpg"


def resolver(ip):
    return lambda host, port, type=0: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]


@pytest.mark.parametrize("url,ip,msg", [
    ("http://exemplo.com/a.jpg", "93.184.216.34", "https"),
    ("https://user:pw@exemplo.com/a.jpg", "93.184.216.34", "usuário"),
    ("https://exemplo.com:8443/a.jpg", "93.184.216.34", "porta"),
    ("https://interno.local/a.jpg", "127.0.0.1", "interno"),
    ("https://interno.local/a.jpg", "10.0.0.5", "interno"),
    ("https://interno.local/a.jpg", "169.254.169.254", "interno"),  # cloud metadata
    ("https://interno.local/a.jpg", "100.64.1.1", "interno"),
    ("https://interno.local/a.jpg", "::1", "interno"),
])
def test_ssrf_guard(url, ip, msg):
    with pytest.raises(safe_fetch.FetchRefused, match=msg):
        safe_fetch.check_url(url, resolve=resolver(ip))


def test_public_address_passes_and_content_is_checked(monkeypatch, tmp_path):
    assert safe_fetch.check_url("https://cdn.exemplo.com/a.jpg", resolve=resolver("93.184.216.34"))
    monkeypatch.setattr(safe_fetch, "check_url", lambda url: url)

    class Resp:
        def __init__(self, data):
            self.data = data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            return self.data[:n]

    class Opener:
        def __init__(self, data):
            self.data = data

        def open(self, req, timeout):
            return Resp(self.data)

    from mla_api.routers.media import sniff_image
    png = make_png(tmp_path / "p.png", 10, 10).read_bytes()
    assert safe_fetch.fetch_image("https://x/a.png", sniff_image, Opener(png))[1] == "image/png"
    with pytest.raises(safe_fetch.FetchRefused, match="não devolveu uma imagem"):
        safe_fetch.fetch_image("https://x/a.png", sniff_image, Opener(b"<html>"))
    monkeypatch.setattr(safe_fetch, "MAX_BYTES", 10)
    with pytest.raises(safe_fetch.FetchRefused, match="10 MB"):
        safe_fetch.fetch_image("https://x/a.png", sniff_image, Opener(png))


class FakeProvider:
    """Test double: returns a different valid PNG. External, so consent is required."""
    name = "teste-local"
    external = True
    max_prompt = 1000

    def __init__(self, tmp_path):
        self.png = make_png(tmp_path / "edited.png", 20, 20, (255, 255, 255)).read_bytes()
        self.calls = []

    def edit(self, image, content_type, prompt):
        self.calls.append(prompt)
        return self.png


@pytest.fixture
def org(api, app, tmp_path):
    api.register("img@example.com", org="Imagens Demo")
    o = f"/api/orgs/{api.org_id()}"
    p = api.post(f"{o}/products", json={"sku": "IMG-1", "name": "Vaso decorativo", "gtin": "7891234567895"}).json()
    png = make_png(tmp_path / "orig.png", 30, 30).read_bytes()
    up = api.post(f"{o}/products/{p['id']}/images/upload", files={"file": ("orig.png", png, "image/png")}).json()
    return api, app, o, p, up, png


def test_ai_not_configured_is_explicit(org):
    api, app, o, p, up, _ = org
    st = api.get(f"{o}/images/ai/status").json()
    assert st["configured"] is False and "Nenhum provedor" in st["message"]
    r = api.post(f"{o}/products/{p['id']}/images/{up['id']}/ai-edit", json={"prompt": "Remova o fundo"})
    assert r.status_code == 409


def test_ai_version_review_and_primary(org, tmp_path):
    api, app, o, p, up, png = org
    provider = FakeProvider(tmp_path)
    app.state.image_ai = provider
    url = f"{o}/products/{p['id']}/images/{up['id']}/ai-edit"
    assert api.post(url, json={"prompt": "Remova o fundo e deixe branco"}).status_code == 409  # no consent
    v = api.post(url, json={"prompt": "Remova o fundo e deixe branco", "consent": True}).json()
    assert (v["source"], v["status"], v["parent_image_id"], v["provider"]) == ("ia", "pending", up["id"], "teste-local")
    assert v["prompt"] == "Remova o fundo e deixe branco" and provider.calls == ["Remova o fundo e deixe branco"]
    # The original is preserved byte for byte.
    assert api.get(f"{o}/products/{p['id']}/images/{up['id']}/file").content == png
    assert api.post(f"{o}/products/{p['id']}/images/{v['id']}/primary").status_code == 409  # pending
    ok = api.post(f"{o}/products/{p['id']}/images/{v['id']}/review", json={"decision": "approve", "set_primary": True}).json()
    assert ok["status"] == "approved" and ok["reviewed_at"]
    imgs = api.get(f"{o}/products/{p['id']}/images").json()
    assert imgs[0]["id"] == v["id"] and imgs[1]["id"] == up["id"]
    v2 = api.post(url, json={"prompt": "Melhore a iluminação", "consent": True}).json()
    assert api.post(f"{o}/products/{p['id']}/images/{v2['id']}/review", json={"decision": "reject"}).json()["status"] == "rejected"
    audit = [e["action"] for e in api.get(f"{o}/audit").json()]
    assert "image.ai_edited" in audit and "image.approved" in audit and "image.rejected" in audit


def test_only_approved_images_reach_sheets(org, app):
    import uuid as _uuid

    from mla_api.services.listing_data import load_products
    api, _, o, p, up, _ = org
    base = f"/api/orgs/{o.rsplit('/', 1)[1]}/products/{p['id']}/images"
    imgs = api.post(base, json=[{"official_url": URL}]).json()
    gestor = next(i for i in imgs if i["official_url"])
    assert gestor["source"] == "gestor"
    api.post(f"{base}/{gestor['id']}/review", json={"decision": "reject"})
    org_id = _uuid.UUID(o.rsplit("/", 1)[1])
    with app.state.sessionmaker() as db:
        data = load_products(db, org_id, [_uuid.UUID(p["id"])])[0]
    assert data.photo_urls == []  # rejected Gestor URL is not exported


def test_import_from_url_and_overview(org, app, tmp_path):
    api, _, o, p, up, _ = org
    png = make_png(tmp_path / "remote.png", 40, 40).read_bytes()
    app.state.image_fetcher = lambda url, sniff: (png, sniff(png))
    r = api.post(f"{o}/products/{p['id']}/images/from-url", json={"url": "https://cdn.exemplo.com/vaso.png"}).json()
    assert r["source"] == "url_externa" and r["external_url"] == "https://cdn.exemplo.com/vaso.png" and r["has_file"]
    app.state.image_fetcher = None
    blocked = api.post(f"{o}/products/{p['id']}/images/from-url", json={"url": "http://127.0.0.1/x.png"})
    assert blocked.status_code == 422
    ov = api.get(f"{o}/images/products", params={"q": "7891234567895"}).json()["items"]
    assert ov[0]["sku"] == "IMG-1" and ov[0]["images"] == 2 and ov[0]["approved"] == 2


def test_isolation(org, new_api):
    api, _, o, p, up, _ = org
    other = new_api()
    other.register("outra@example.com", org="Outra")
    o2 = f"/api/orgs/{other.org_id()}"
    assert other.post(f"{o2}/products/{p['id']}/images/{up['id']}/review", json={"decision": "reject"}).status_code == 404
    assert other.post(f"{o2}/products/{p['id']}/images/{up['id']}/ai-edit", json={"prompt": "xxx"}).status_code in (404, 409)
    assert other.get(f"{o2}/images/products").json()["items"] == []
    assert api.get(f"{o}/products/{p['id']}/images").json()[0]["status"] == "approved"
