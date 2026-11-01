from __future__ import annotations

import time

import pytest

from mla_api.domain.catalog import gtin_valid


@pytest.fixture
def owner(api):
    api.register("a@example.com")
    return api, api.org_id()


def test_crud_and_pendings(owner):
    api, org = owner
    p = api.add_product(org, "FO-100", brand="Tecfil", gtin="7891234567895", price_cents=2590,
                        description="Filtro de óleo")
    assert p["pendings"] == []
    r = api.patch(f"/api/orgs/{org}/products/{p['id']}", json={"price_cents": None, "brand": ""})
    fields = {x["field"]: x["severity"] for x in r.json()["pendings"]}
    assert fields == {"price_cents": "error", "brand": "warning"}
    assert api.get(f"/api/orgs/{org}/products/{p['id']}").json()["sku"] == "FO-100"
    assert api.delete(f"/api/orgs/{org}/products/{p['id']}").status_code == 204
    assert api.get(f"/api/orgs/{org}/products/{p['id']}").status_code == 404


def test_duplicate_sku_conflicts(owner):
    api, org = owner
    api.add_product(org, "A")
    assert api.post(f"/api/orgs/{org}/products", json={"sku": "A", "name": "x"}).status_code == 409


@pytest.mark.parametrize("body", [
    {"sku": "COM ESPACO", "name": "x"},
    {"sku": "", "name": "x"},
    {"sku": "A", "name": ""},
    {"sku": "A", "name": "x", "gtin": "123"},
    {"sku": "A", "name": "x", "stock": -1},
    {"sku": "A", "name": "x", "price_cents": -5},
    {"sku": "A", "name": "x", "status": "published"},
])
def test_invalid_input_refused(owner, body):
    api, org = owner
    assert api.post(f"/api/orgs/{org}/products", json=body).status_code == 422


def test_invalid_gtin_check_digit_is_a_warning_not_a_block(owner):
    api, org = owner
    p = api.add_product(org, "G", gtin="7891234567890", price_cents=100, brand="X")
    assert not gtin_valid("7891234567890")
    assert [x["field"] for x in p["pendings"] if x["severity"] == "warning"] == ["gtin"]


def test_search_filter_pagination(owner):
    api, org = owner
    for i in range(30):
        api.add_product(org, f"SKU-{i:02d}", brand="Bosch" if i % 3 == 0 else "NGK", status="active" if i < 10 else "draft")
    r = api.get(f"/api/orgs/{org}/products", params={"q": "bosch", "limit": 5, "sort": "sku"}).json()
    assert r["total"] == 10 and [p["sku"] for p in r["items"]] == ["SKU-00", "SKU-03", "SKU-06", "SKU-09", "SKU-12"]
    assert api.get(f"/api/orgs/{org}/products", params={"status": "active"}).json()["total"] == 10
    page2 = api.get(f"/api/orgs/{org}/products", params={"limit": 20, "offset": 20, "sort": "sku"}).json()
    assert len(page2["items"]) == 10
    # LIKE wildcards in the search are literal noise, not "match everything".
    assert api.get(f"/api/orgs/{org}/products", params={"q": "%"}).json()["total"] == 30


def test_dashboard_counts_are_real(owner):
    api, org = owner
    api.add_product(org, "OK", brand="X", price_cents=100, description="d")
    api.add_product(org, "NO-PRICE", brand="X")
    d = api.get(f"/api/orgs/{org}/dashboard").json()
    assert (d["products_total"], d["products_complete"], d["products_with_pendings"]) == (2, 1, 1)
    assert d["batches_total"] == 0 and d["exports_total"] is None  # no writer yet: no fake zero for exports
    assert d["recent_activity"][0]["action"] == "product.created"


@pytest.mark.perf
@pytest.mark.parametrize("n", [10, 100, 1000, 5000])
def test_volume_list_and_dashboard(app, owner, n):
    """Volume scenario (not a Mercado Livre limit): rows inserted directly, then read through the API."""
    from mla_api.models import Product
    api, org = owner
    import uuid
    with app.state.sessionmaker() as db:
        db.add_all(Product(organization_id=uuid.UUID(org), sku=f"S{i}", name=f"P{i}", brand="B" if i % 2 else "",
                           price_cents=100, description="d", stock=1) for i in range(n))
        db.commit()
    t0 = time.perf_counter()
    d = api.get(f"/api/orgs/{org}/dashboard").json()
    page = api.get(f"/api/orgs/{org}/products", params={"limit": 50}).json()
    elapsed = time.perf_counter() - t0
    assert d["products_total"] == n and d["products_complete"] == n // 2
    assert page["total"] == n and len(page["items"]) == min(n, 50)
    print(f"\n[perf] n={n}: dashboard + first page in {elapsed * 1000:.0f} ms (SQLite)")
    assert elapsed < 10


def test_timestamps_are_serialized_with_timezone(owner):
    """SQLite returns naive datetimes; without an offset the browser shows UTC as local time."""
    api, org = owner
    p = api.add_product(org, "TZ")
    p = api.get(f"/api/orgs/{org}/products/{p['id']}").json()
    activity = api.get(f"/api/orgs/{org}/dashboard").json()["recent_activity"]
    for value in (p["created_at"], p["updated_at"], activity[0]["created_at"]):
        assert value.endswith("Z") or value.endswith("+00:00"), value
