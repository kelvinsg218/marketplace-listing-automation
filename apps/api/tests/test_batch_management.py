"""Batch management (duplicate, delete drafts, archive, resume phase) and category filters. Fictitious data."""
from __future__ import annotations

import pytest
from synthetic_template import build_official_like

SHEET = "Peças de Teste"
URL = "https://http2.mlstatic.com/D_NQ_NP_000000-MLA00000000000_000000-F.jpg"


@pytest.fixture
def org(api):
    api.register("lotes@example.com", org="Lotes Demo")
    return api, f"/api/orgs/{api.org_id()}"


def test_duplicate_archive_resume_and_delete(org):
    api, o = org
    p1 = api.post(f"{o}/products", json={"sku": "A1", "name": "Produto A"}).json()
    p2 = api.post(f"{o}/products", json={"sku": "B1", "name": "Produto B"}).json()
    b = api.post(f"{o}/batches", json={"name": "Lote base"}).json()
    url = f"{o}/batches/{b['id']}"
    api.put(f"{url}/items", json={"product_ids": [p1["id"], p2["id"]]})
    assert api.patch(url, json={"name": "Lote renomeado"}).json()["name"] == "Lote renomeado"
    assert api.patch(url, json={"last_phase": 3}).json()["last_phase"] == 3

    dup = api.post(f"{url}/duplicate").json()
    assert dup["name"] == "Lote renomeado (cópia)" and dup["items"] == 2 and dup["status"] == "draft"
    assert dup["history"][0]["duplicated_from"] == "Lote renomeado"

    api.post(f"{url}/archive")
    assert [x["id"] for x in api.get(f"{o}/batches").json()] == [dup["id"]]
    assert [x["id"] for x in api.get(f"{o}/batches", params={"archived": True}).json()] == [b["id"]]
    assert api.post(f"{url}/unarchive").json()["archived"] is False

    assert api.delete(f"{o}/batches/{dup['id']}").status_code == 204
    assert api.get(f"{o}/batches/{dup['id']}").status_code == 404
    assert api.get(f"{o}/products").json()["total"] == 2  # products untouched


def test_batches_with_files_cannot_be_deleted(org):
    api, o = org
    acc = api.post(f"{o}/seller-accounts", json={"label": "Conta"}).json()
    tpl = api.post(f"{o}/templates", data={"seller_account_id": acc["id"], "source": "categories"},
                   files={"file": ("t.xlsx", build_official_like(), "application/octet-stream")}).json()
    api.put(f"{o}/templates/{tpl['id']}/mapping", json={"sheet_name": SHEET, "header_row": 3, "rules": {
        "A": {"source": "name"}, "D": {"source": "photos"}, "F": {"source": "stock"}, "G": {"source": "price"},
        "L": {"source": "brand"}, "M": {"source": "sku"}}})
    p = api.post(f"{o}/products", json={"sku": "C1", "name": "Produto C", "brand": "M", "price_cents": 1000,
                                        "stock": 1}).json()
    api.post(f"{o}/products/{p['id']}/images", json=[{"official_url": URL}])
    b = api.post(f"{o}/batches", json={"name": "L"}).json()
    url = f"{o}/batches/{b['id']}"
    api.patch(url, json={"seller_account_id": acc["id"]})
    api.patch(url, json={"template_id": tpl["id"], "sheet_name": SHEET})
    api.put(f"{url}/items", json={"product_ids": [p["id"]]})
    assert api.post(f"{url}/export").status_code == 201
    r = api.delete(url)
    assert r.status_code == 409 and "arquive" in r.json()["detail"]
    assert api.get(url).json()["exports"] == 1
    # Resuming works even on locked (sent) batches: it only stores where the user stopped.
    api.post(f"{url}/confirm-sent", json={})
    assert api.patch(url, json={"last_phase": 5}).json()["last_phase"] == 5
    assert api.patch(url, json={"name": "x"}).status_code == 409


def test_category_filters(org):
    api, o = org
    api.post(f"{o}/categories/seed-defaults")
    cats = {c["path"]: c["id"] for c in api.get(f"{o}/categories").json()}
    freio = api.post(f"{o}/products", json={"sku": "F1", "name": "Pastilha de freio"}).json()
    motor = api.post(f"{o}/products", json={"sku": "M1", "name": "Filtro de óleo"}).json()
    api.post(f"{o}/products", json={"sku": "S1", "name": "Sem categoria"})
    api.post(f"{o}/classification/confirm", json={"product_ids": [freio["id"]], "category_id": cats["Autopeças > Freios"]})
    api.post(f"{o}/classification/confirm", json={"product_ids": [motor["id"]], "category_id": cats["Autopeças > Motor"]})
    by_leaf = api.get(f"{o}/products", params={"category_id": cats["Autopeças > Freios"]}).json()
    assert [p["sku"] for p in by_leaf["items"]] == ["F1"]
    by_parent = api.get(f"{o}/products", params={"category_id": cats["Autopeças"], "sort": "sku"}).json()
    assert [p["sku"] for p in by_parent["items"]] == ["F1", "M1"]  # parent includes sub-categories
    b = api.post(f"{o}/batches", json={"name": "Autopeças"}).json()
    r = api.put(f"{o}/batches/{b['id']}/items", json={"all_matching": {"category_id": cats["Autopeças"]}})
    assert r.json()["items"] == 2
    assert api.put(f"{o}/batches/{b['id']}/items", json={"all_matching": {"category_id": "x"}}).status_code == 422


def test_isolation(org, new_api):
    api, o = org
    b = api.post(f"{o}/batches", json={"name": "Meu lote"}).json()
    other = new_api()
    other.register("outro@example.com", org="Outra")
    o2 = f"/api/orgs/{other.org_id()}"
    for method, path in [("post", f"{o2}/batches/{b['id']}/duplicate"), ("delete", f"{o2}/batches/{b['id']}"),
                         ("post", f"{o2}/batches/{b['id']}/archive")]:
        assert getattr(other, method)(path).status_code == 404
    assert api.get(f"{o}/batches/{b['id']}").status_code == 200
