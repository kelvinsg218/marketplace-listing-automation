"""Variants, Central de Fotos, seller accounts, templates, mapping and batches through the API (synthetic files)."""
from __future__ import annotations

import pytest
from synthetic_template import build

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
MLSTATIC = "https://http2.mlstatic.com/D_NQ_NP_903478-MLM72199717417_102023-F.jpg"
MLSTATIC2 = "https://http2.mlstatic.com/D_NQ_NP_929525-MLM72199413355_102023-F.jpg"


@pytest.fixture
def owner(api):
    api.register("owner@example.com", org="Loja A")
    return api, api.org_id()


def upload_template(api, org, account_id, data=None, name="anunciador.xlsx", source="categories"):
    return api.post(f"/api/orgs/{org}/templates", data={"seller_account_id": account_id, "source": source},
                    files={"file": (name, data or build(), "application/octet-stream")})


@pytest.fixture
def setup(owner):
    api, org = owner
    acc = api.post(f"/api/orgs/{org}/seller-accounts", json={"label": "Conta principal"}).json()
    data = build()  # build() embeds the creation time, so keep the exact bytes that were uploaded
    tpl = upload_template(api, org, acc["id"], data=data)
    assert tpl.status_code == 201, tpl.text
    return api, org, acc, {**tpl.json(), "_bytes": data}


# --- variants ---------------------------------------------------------------------------------------------------
def test_variants_crud_and_sku_uniqueness(owner):
    api, org = owner
    p = api.add_product(org, "CAM-1", price_cents=5000)
    base = f"/api/orgs/{org}/products/{p['id']}/variants"
    v = api.post(base, json={"sku": "CAM-1-P", "attributes": {"Tamanho": "P"}, "gtin": "7891234567895"})
    assert v.status_code == 201 and v.json()["gtin_valid"] is True
    assert api.post(base, json={"sku": "CAM-1", "attributes": {"Tamanho": "M"}}).status_code == 409  # product SKU
    assert api.post(base, json={"sku": "CAM-1-P", "attributes": {"Tamanho": "M"}}).status_code == 409
    assert api.post(base, json={"sku": "X", "attributes": {}}).status_code == 422
    vid = v.json()["id"]
    upd = api.put(f"{base}/{vid}", json={"sku": "CAM-1-P", "attributes": {"Tamanho": "PP"}, "stock": 4})
    assert upd.json()["attributes"] == {"Tamanho": "PP"} and upd.json()["stock"] == 4
    assert len(api.get(base).json()) == 1
    assert api.delete(f"{base}/{vid}").status_code == 204 and api.get(base).json() == []


# --- photos -----------------------------------------------------------------------------------------------------
def test_photo_upload_is_checked_by_content_and_served_only_to_members(owner, new_api):
    api, org = owner
    p = api.add_product(org, "F-1")
    base = f"/api/orgs/{org}/products/{p['id']}/images"
    ok = api.post(f"{base}/upload", files={"file": ("foto.png", JPEG, "image/png")})
    assert ok.status_code == 201 and ok.json()["content_type"] == "image/jpeg"  # bytes win over declared type
    bad = api.post(f"{base}/upload", files={"file": ("foto.jpg", b"<script>alert(1)</script>", "image/jpeg")})
    assert bad.status_code == 415
    f = api.get(f"{base}/{ok.json()['id']}/file")
    assert f.status_code == 200 and f.content == JPEG and f.headers["x-content-type-options"] == "nosniff"
    other = new_api()
    other.register("other@example.com", org="Loja B")
    assert other.get(f"{base}/{ok.json()['id']}/file").status_code == 404


def test_photo_upload_size_limit(owner, monkeypatch):
    from mla_api.routers import media
    monkeypatch.setattr(media, "MAX_IMAGE_BYTES", 100)
    api, org = owner
    p = api.add_product(org, "F-2")
    r = api.post(f"/api/orgs/{org}/products/{p['id']}/images/upload", files={"file": ("a.jpg", JPEG, "image/jpeg")})
    assert r.status_code == 413


def test_official_urls_from_gestor_and_order(owner):
    api, org = owner
    p = api.add_product(org, "F-3")
    base = f"/api/orgs/{org}/products/{p['id']}/images"
    # The text copied from the Gestor de fotos holds several URLs separated by commas (P3 p.4).
    r = api.post(base, json=[{"official_url": f"{MLSTATIC},{MLSTATIC2}"}])
    assert r.status_code == 201 and [i["official_url"] for i in r.json()] == [MLSTATIC, MLSTATIC2]
    assert api.post(base, json=[{"official_url": "http://inseguro.com/a.jpg"}]).status_code == 422
    ext = api.post(base, json=[{"official_url": "https://cdn.exemplo.com/a.jpg"}]).json()[-1]
    assert "Não está confirmado" in ext["url_problem"]
    ids = [i["id"] for i in api.get(base).json()]
    reordered = api.put(f"{base}/order", json={"ids": list(reversed(ids))}).json()
    assert [i["id"] for i in reordered] == list(reversed(ids))
    assert api.put(f"{base}/order", json={"ids": ids[:1]}).status_code == 422
    status = api.get(f"/api/orgs/{org}/photos/status").json()
    assert status[0]["with_url"] == 3 and status[0]["without_url"] == 0


def test_channel_data_catalog_code(owner):
    api, org = owner
    p = api.add_product(org, "C-1")
    url = f"/api/orgs/{org}/products/{p['id']}/channels/mercadolivre"
    assert api.get(url).json()["catalog_code"] == ""
    assert api.put(url, json={"catalog_code": "MLB12345"}).json()["catalog_code"] == "MLB12345"
    assert api.put(url, json={"catalog_code": "MLB 12;"}).status_code == 422
    assert api.put(f"/api/orgs/{org}/products/{p['id']}/channels/shopee", json={}).status_code == 404


# --- templates --------------------------------------------------------------------------------------------------
def test_template_registry(setup, app):
    api, org, acc, tpl = setup
    assert tpl["status"] == "inspected" and tpl["seller_account_label"] == "Conta principal"
    assert tpl["deadline_date"].endswith("-09-10")  # year inferred from the upload date, so unconfirmed
    assert tpl["deadline_confirmed"] is False and tpl["source"] == "categories"
    assert upload_template(api, org, acc["id"], data=tpl["_bytes"]).status_code == 409  # same bytes twice
    assert upload_template(api, org, acc["id"], name="x.csv").status_code == 415
    assert upload_template(api, org, acc["id"], data=b"PK\x03\x04broken", name="b.xlsx").json()["status"] == "invalid"
    # The original is kept byte for byte.
    assert api.get(f"/api/orgs/{org}/templates/{tpl['id']}/file").content == tpl["_bytes"]
    conf = api.patch(f"/api/orgs/{org}/templates/{tpl['id']}", json={"deadline_date": "2027-01-15"}).json()
    assert conf["deadline_confirmed"] is True and conf["expired"] is False


def test_mapping_suggestions_and_save(setup):
    api, org, acc, tpl = setup
    url = f"/api/orgs/{org}/templates/{tpl['id']}/mapping"
    assert api.get(url, params={"sheet": "Ajuda"}).status_code == 422
    m = api.get(url, params={"sheet": "Biscoitos", "header_row": 3}).json()
    sug = {c["header"]: c["suggestion"] for c in m["columns"]}
    assert sug["Código do catálogo ML"] == "catalog_code" and sug["Fotos"] == "photos" and sug["SKU"] == "sku"
    assert m["header_row_confirmed"] is False
    body = {"sheet_name": "Biscoitos", "header_row": 3,
            "rules": {"B": {"source": "name"}, "C": {"source": "sku"}, "D": {"source": "price"},
                      "G": {"source": "photos"}}}
    saved = api.put(url, json=body).json()
    assert saved["header_row_confirmed"] is True and saved["rules"]["G"]["source"] == "photos"
    assert api.put(url, json={**body, "rules": {"Z": {"source": "name"}}}).status_code == 422
    assert api.put(url, json={**body, "rules": {"B": {"source": "senha"}}}).status_code == 422


# --- batches ----------------------------------------------------------------------------------------------------
def make_ready_batch(api, org, acc, tpl, product_ids):
    api.patch(f"/api/orgs/{org}/templates/{tpl['id']}", json={"deadline_date": "2099-12-31"})
    api.put(f"/api/orgs/{org}/templates/{tpl['id']}/mapping", json={
        "sheet_name": "Biscoitos", "header_row": 3,
        "rules": {"B": {"source": "name"}, "C": {"source": "sku"}, "D": {"source": "price"},
                  "G": {"source": "photos"}}})
    b = api.post(f"/api/orgs/{org}/batches", json={"name": "Lote 1"}).json()
    url = f"/api/orgs/{org}/batches/{b['id']}"
    api.patch(url, json={"seller_account_id": acc["id"]})
    api.patch(url, json={"template_id": tpl["id"], "sheet_name": "Biscoitos"})
    api.put(f"{url}/items", json={"mode": "add", "product_ids": product_ids})
    return url


def test_batch_flow_validation_preview_and_no_fake_publication(setup):
    api, org, acc, tpl = setup
    good = api.add_product(org, "B-1", brand="Marca", price_cents=990, stock=5, description="d")
    api.post(f"/api/orgs/{org}/products/{good['id']}/images", json=[{"official_url": MLSTATIC}])
    bad = api.add_product(org, "B-2")
    url = make_ready_batch(api, org, acc, tpl, [good["id"], bad["id"]])

    v = api.post(f"{url}/validate").json()
    assert v["summary"]["products"] == 2 and v["summary"]["with_errors"] == 1 and v["summary"]["ready"] is False
    assert v["products"][0]["sku"] == "B-2"  # worst first
    assert api.get(url).json()["status"] == "needs_fix"

    api.put(f"{url}/items", json={"mode": "remove", "product_ids": [bad["id"]]})
    assert api.get(url).json()["status"] == "draft"  # content changed: validation invalidated
    v = api.post(f"{url}/validate").json()
    assert v["summary"]["ready"] is True and api.get(url).json()["status"] == "ready"

    prev = api.get(f"{url}/preview").json()
    assert prev["total_rows"] == 1 and prev["rows"][0]["values"]["G"] == MLSTATIC
    assert prev["rows"][0]["values"]["D"] == "9.90"

    exp = api.post(f"{url}/export")
    # This synthetic file lacks the official data-row structure, so the writer refuses instead of guessing.
    assert exp.status_code == 409 and "estrutura oficial" in exp.json()["detail"]
    # Sent / result states need an exported batch and explicit confirmation: never inferred.
    assert api.post(f"{url}/confirm-sent", json={}).status_code == 409
    assert api.post(f"{url}/confirm-result", json={}).status_code == 409
    events = [h["event"] for h in api.get(url).json()["history"]]
    assert events[0] == "created" and "items" in events


def test_template_must_belong_to_batch_account(setup):
    api, org, acc, tpl = setup
    other = api.post(f"/api/orgs/{org}/seller-accounts", json={"label": "Conta 2"}).json()
    b = api.post(f"/api/orgs/{org}/batches", json={"name": "L"}).json()
    url = f"/api/orgs/{org}/batches/{b['id']}"
    api.patch(url, json={"seller_account_id": other["id"]})
    r = api.patch(url, json={"template_id": tpl["id"]})
    assert r.status_code == 409 and "própria conta" in r.json()["detail"]


def test_expired_template_blocks(setup):
    api, org, acc, tpl = setup
    p = api.add_product(org, "E-1", brand="M", price_cents=100, stock=1)
    url = make_ready_batch(api, org, acc, tpl, [p["id"]])
    api.patch(f"/api/orgs/{org}/templates/{tpl['id']}", json={"deadline_date": "2020-01-01"})
    v = api.post(f"{url}/validate").json()
    assert any(i["code"] == "template_expired" for i in v["template_issues"]) and v["summary"]["ready"] is False


def test_select_all_matching(setup):
    api, org, acc, tpl = setup
    for i in range(5):
        api.add_product(org, f"S-{i}", brand="Bosch" if i < 3 else "NGK")
    b = api.post(f"/api/orgs/{org}/batches", json={"name": "L"}).json()
    r = api.put(f"/api/orgs/{org}/batches/{b['id']}/items", json={"mode": "add", "all_matching": {"q": "bosch"}})
    assert r.json()["items"] == 3


# --- isolation --------------------------------------------------------------------------------------------------
def test_new_resources_are_isolated_between_organizations(setup, new_api):
    api, org, acc, tpl = setup
    p = api.add_product(org, "ISO-1")
    b = api.post(f"/api/orgs/{org}/batches", json={"name": "L"}).json()
    intruder = new_api()
    intruder.register("intruder@example.com", org="Loja B")
    org_b = intruder.org_id()
    for path in [f"/api/orgs/{org}/templates", f"/api/orgs/{org}/templates/{tpl['id']}",
                 f"/api/orgs/{org}/templates/{tpl['id']}/file", f"/api/orgs/{org}/batches/{b['id']}",
                 f"/api/orgs/{org}/seller-accounts", f"/api/orgs/{org}/products/{p['id']}/variants",
                 f"/api/orgs/{org}/photos/status"]:
        assert intruder.get(path).status_code == 404, path
    # Through their own organization: foreign ids are invisible or dropped.
    assert intruder.get(f"/api/orgs/{org_b}/templates/{tpl['id']}").status_code == 404
    assert intruder.get(f"/api/orgs/{org_b}/products/{p['id']}/images").status_code == 404
    acc_b = intruder.post(f"/api/orgs/{org_b}/seller-accounts", json={"label": "B"}).json()
    b2 = intruder.post(f"/api/orgs/{org_b}/batches", json={"name": "B"}).json()
    r = intruder.put(f"/api/orgs/{org_b}/batches/{b2['id']}/items", json={"product_ids": [p["id"]]})
    assert r.json()["items"] == 0
    r = intruder.patch(f"/api/orgs/{org_b}/batches/{b2['id']}", json={"seller_account_id": acc["id"]})
    assert r.status_code == 404
    # The same official file uploaded by another organization is a separate, private record.
    assert upload_template(intruder, org_b, acc_b["id"]).status_code == 201
    assert len(api.get(f"/api/orgs/{org}/templates").json()) == 1


def test_viewer_cannot_change_bulk_listing(setup, new_api):
    api, org, acc, tpl = setup
    viewer = new_api()
    viewer.register("viewer@example.com", org="Pessoal")
    api.post(f"/api/orgs/{org}/members", json={"email": "viewer@example.com", "role": "viewer"})
    assert viewer.get(f"/api/orgs/{org}/templates").status_code == 200
    assert upload_template(viewer, org, acc["id"], data=build(hidden_sheet=False)).status_code == 403
    assert viewer.post(f"/api/orgs/{org}/batches", json={"name": "x"}).status_code == 403
    assert viewer.post(f"/api/orgs/{org}/seller-accounts", json={"label": "x"}).status_code == 403
