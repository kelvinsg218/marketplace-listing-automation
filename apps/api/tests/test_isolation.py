"""Multi-organization isolation. Application layer (any database) + PostgreSQL row-level security (marked)."""
from __future__ import annotations

import pytest
from conftest import random_uuid
from sqlalchemy import inspect, select, text

from mla_api.db import Base, make_engine, make_sessionmaker, set_tenant
from mla_api.models import TENANT_TABLES, Organization, Product

# Tables with organization_id that are deliberately outside RLS (membership lookup crosses organizations).
RLS_EXEMPT = {"memberships"}


@pytest.fixture
def two_orgs(new_api):
    a, b = new_api(), new_api()
    a.register("a@example.com", org="Empresa A")
    b.register("b@example.com", org="Empresa B")
    org_a, org_b = a.org_id(), b.org_id()
    pa = a.add_product(org_a, "SKU-1", price_cents=1000)
    pb = b.add_product(org_b, "SKU-1", price_cents=2000)  # same SKU in another organization is fine
    return a, b, org_a, org_b, pa, pb


def test_member_sees_only_own_products(two_orgs):
    a, b, org_a, org_b, pa, pb = two_orgs
    items = a.get(f"/api/orgs/{org_a}/products").json()["items"]
    assert [p["id"] for p in items] == [pa["id"]]


def test_non_member_gets_404_on_every_org_route(two_orgs):
    a, b, org_a, org_b, pa, pb = two_orgs
    for method, path, body in [
        ("get", f"/api/orgs/{org_b}", None),
        ("get", f"/api/orgs/{org_b}/products", None),
        ("get", f"/api/orgs/{org_b}/products/{pb['id']}", None),
        ("patch", f"/api/orgs/{org_b}/products/{pb['id']}", {"name": "hack"}),
        ("delete", f"/api/orgs/{org_b}/products/{pb['id']}", None),
        ("post", f"/api/orgs/{org_b}/products", {"sku": "X", "name": "x"}),
        ("get", f"/api/orgs/{org_b}/dashboard", None),
        ("get", f"/api/orgs/{org_b}/members", None),
        ("get", f"/api/orgs/{org_b}/audit", None),
        ("get", f"/api/orgs/{random_uuid()}/products", None),
    ]:
        r = getattr(a, method)(path, **({"json": body} if body else {}))
        assert r.status_code == 404, (method, path, r.status_code)
    assert b.get(f"/api/orgs/{org_b}/products/{pb['id']}").json()["name"] == "Produto SKU-1"


def test_product_id_of_other_org_through_own_org_route(two_orgs):
    """Own organization in the URL, foreign product id: still 404 and untouched."""
    a, b, org_a, org_b, pa, pb = two_orgs
    assert a.get(f"/api/orgs/{org_a}/products/{pb['id']}").status_code == 404
    assert a.patch(f"/api/orgs/{org_a}/products/{pb['id']}", json={"name": "hack"}).status_code == 404
    assert a.delete(f"/api/orgs/{org_a}/products/{pb['id']}").status_code == 404
    assert b.get(f"/api/orgs/{org_b}/products/{pb['id']}").json()["price_cents"] == 2000


def test_dashboard_and_audit_scoped(two_orgs):
    a, b, org_a, org_b, pa, pb = two_orgs
    b.add_product(org_b, "SKU-2")
    assert a.get(f"/api/orgs/{org_a}/dashboard").json()["products_total"] == 1
    assert b.get(f"/api/orgs/{org_b}/dashboard").json()["products_total"] == 2
    audit_a = a.get(f"/api/orgs/{org_a}/audit").json()
    assert all(e["target_id"] != pb["id"] for e in audit_a)


def test_unauthenticated_gets_401(app, two_orgs):
    from conftest import Api
    *_, org_a, org_b, pa, pb = two_orgs
    assert Api(app).get(f"/api/orgs/{org_a}/products").status_code == 401


def test_every_org_owned_table_is_protected():
    org_tables = {t.name for t in Base.metadata.sorted_tables if "organization_id" in t.c}
    assert org_tables - RLS_EXEMPT == set(TENANT_TABLES)


# --- PostgreSQL row-level security ------------------------------------------------------------------------------
@pytest.mark.postgres
def test_rls_hides_rows_even_without_application_filter(pg_url, tmp_path):
    from alembic import command
    from alembic.config import Config
    from conftest import Api, make_settings
    from mla_api.main import create_app

    engine = make_engine(pg_url)
    with engine.connect() as c:
        if c.execute(text("select rolsuper from pg_roles where rolname = current_user")).scalar():
            pytest.skip("Conectado como superusuário: o PostgreSQL ignora RLS para superusuários.")
    with engine.begin() as c:
        c.execute(text("drop schema public cascade; create schema public"))
    cfg = Config(str(__import__("pathlib").Path(__file__).parents[1] / "alembic.ini"))
    cfg.attributes["database_url"] = pg_url
    command.upgrade(cfg, "head")
    assert {"products", "audit_events"} <= set(inspect(engine).get_table_names())

    app = create_app(make_settings(tmp_path, database_url=pg_url))
    a, b = Api(app), Api(app)
    a.register("a@example.com", org="A")
    b.register("b@example.com", org="B")
    org_a, org_b = a.org_id(), b.org_id()
    a.add_product(org_a, "A-1")
    b.add_product(org_b, "B-1")

    sm = make_sessionmaker(engine)
    with sm() as db:  # no tenant: nothing visible, even with a query that forgets organization_id
        assert db.scalars(select(Product)).all() == []
    with sm() as db:
        set_tenant(db, db.scalar(select(Organization.id).where(Organization.name == "A")))
        assert [p.sku for p in db.scalars(select(Product))] == ["A-1"]
        db.commit()  # tenant survives the commit (re-applied on the next transaction)
        assert [p.sku for p in db.scalars(select(Product))] == ["A-1"]
        # Writing a row for another organization is refused by the policy's WITH CHECK.
        db.add(Product(organization_id=org_b, sku="X", name="x", brand="", model="", gtin="", description="",
                       stock=0, status="draft", attributes={}))
        with pytest.raises(Exception):
            db.flush()
    app.state.engine.dispose()
    engine.dispose()
