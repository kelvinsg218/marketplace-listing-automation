"""Deterministic classification (fictitious products)."""
from __future__ import annotations

import time

import pytest

from mla_api.domain.classifier import DEFAULT_TREE, CategoryRule, classify


def rules():
    out = []
    for top, children in DEFAULT_TREE.items():
        for name, kw in children.items():
            out.append(CategoryRule(name, f"{top} > {name}", tuple(kw.get("phrases", [])), tuple(kw.get("words", [])),
                                    tuple(kw.get("exclude", []))))
    return out


@pytest.mark.parametrize("name,desc,expected,confidence", [
    ("Carrinho de controle remoto 4x4 RC", "", "Veículos de controle remoto", "alta"),
    ("Pastilha de freio dianteira cerâmica", "Para disco de freio ventilado", "Freios", "alta"),
    ("Filtro de óleo PSL55", "", "Motor", "alta"),
    ("Vaso decorativo de cerâmica", "", "Vasos", "alta"),
    ("Camiseta manga longa algodão", "", "Camisetas", "alta"),
])
def test_clear_cases_are_high_confidence(name, desc, expected, confidence):
    r = classify(name, desc, {}, rules())
    assert (r.path.split(" > ")[1], r.confidence) == (expected, confidence), r.evidence


def test_single_isolated_word_never_classifies():
    r = classify("Mola", "", {}, rules())  # one word, 1 point
    assert r.category_id is None and r.confidence == "baixa"


def test_word_must_be_whole():
    assert classify("Kit faroleiro", "", {}, rules()).category_id is None  # no partial-word matches


def test_exclusions():
    r = classify("Jogo de pastilhas de freio", "", {}, rules())
    assert r.path.endswith("Freios")  # "jogo de pastilhas" excludes the toy category "Jogos"
    assert classify("Vaso sanitário", "", {}, rules()).category_id is None


def test_ambiguous_needs_confirmation():
    r = classify("Boneco organizador", "", {}, rules())  # one word for two different categories
    assert r.confidence in ("media", "baixa")
    r = classify("Tênis", "Sapato confortável", {}, rules())
    assert r.confidence == "media"  # two single words, no compound expression


def test_attributes_count_as_context():
    r = classify("Peça XYZ-200", "", {"Aplicação": "amortecedor dianteiro"}, rules())
    assert r.path.endswith("Suspensão") and r.confidence == "media"  # phrase only in attributes -> confirm


# --- API ----------------------------------------------------------------------------------------------------------
@pytest.fixture
def org(api):
    api.register("cls@example.com", org="Loja Demo")
    o = f"/api/orgs/{api.org_id()}"
    assert api.post(f"{o}/categories/seed-defaults").json()["created"] > 10
    assert api.post(f"{o}/categories/seed-defaults").json()["created"] == 0  # idempotent
    return api, o


def add(api, o, sku, name, desc=""):
    return api.post(f"{o}/products", json={"sku": sku, "name": name, "description": desc}).json()


def test_run_review_confirm_and_manual_is_kept(org):
    api, o = org
    rc = add(api, o, "RC-1", "Carrinho de controle remoto off-road")
    am = add(api, o, "AMB-1", "Tênis", "Sapato leve")
    add(api, o, "X-1", "Produto genérico 123")
    totals = api.post(f"{o}/classification/run", json={}).json()
    assert (totals["alta"], totals["media"], totals["baixa"]) == (1, 1, 1)
    review = api.get(f"{o}/classification", params={"view": "review"}).json()
    assert review[0]["sku"] == "AMB-1" and review[0]["confidence"] == "media"  # doubtful first
    cats = {c["path"]: c["id"] for c in api.get(f"{o}/categories").json()}
    # Manual decision for the ambiguous one, accept the clear suggestion.
    assert api.post(f"{o}/classification/confirm", json={"product_ids": [am["id"]], "mode": "set",
                                                          "category_id": cats["Moda > Calçados"]}).json()["changed"] == 1
    assert api.post(f"{o}/classification/confirm", json={"product_ids": [rc["id"]], "mode": "accept_suggestion"}).json()["changed"] == 1
    # Re-running never changes confirmed products, even if keywords would now say otherwise.
    api.put(f"{o}/categories/{cats['Moda > Calçados']}", json={"name": "Calçados", "parent_id": next(
        c["parent_id"] for c in api.get(f"{o}/categories").json() if c["path"] == "Moda > Calçados"),
        "keywords": {"phrases": [], "words": ["nada"], "exclude": []}})
    totals = api.post(f"{o}/classification/run", json={}).json()
    assert totals["kept_confirmed"] == 2
    confirmed = {r["sku"]: r["category_path"] for r in api.get(f"{o}/classification", params={"view": "confirmed"}).json()}
    assert confirmed == {"AMB-1": "Moda > Calçados", "RC-1": "Brinquedos > Veículos de controle remoto"}


def test_custom_category_rule_and_ml_category_flag(org):
    api, o = org
    c = api.post(f"{o}/categories", json={"name": "Kits de embreagem", "keywords": {
        "phrases": ["kit de embreagem", "kit de embreagem"], "words": ["embreagem"], "exclude": []},
        "ml_category_id": "MLB0000", "ml_category_confirmed": False}).json()
    assert c["keywords"]["phrases"] == ["kit de embreagem"]  # deduplicated
    assert c["ml_category_confirmed"] is False  # official category stays unconfirmed until the user says so
    p = add(api, o, "KE-1", "Kit de embreagem completo")
    api.post(f"{o}/classification/run", json={"product_ids": [p["id"]]})
    row = api.get(f"{o}/classification", params={"view": "all"}).json()[0]
    assert row["category_path"] == "Kits de embreagem" and row["confidence"] == "alta"
    bad = api.post(f"{o}/categories", json={"name": "X", "ml_category_id": "MLB 1; drop"})
    assert bad.status_code == 422


def test_isolation(org, new_api):
    api, o = org
    p = add(api, o, "RC-9", "Carrinho de controle remoto")
    other = new_api()
    other.register("x@example.com", org="Outra")
    o2 = f"/api/orgs/{other.org_id()}"
    assert other.get(f"{o}/categories").status_code == 404
    assert other.get(f"{o2}/categories").json() == []
    assert other.post(f"{o2}/classification/run", json={}).status_code == 409  # no categories of their own
    other.post(f"{o2}/categories/seed-defaults")
    cat = other.get(f"{o2}/categories").json()[0]["id"]
    r = other.post(f"{o2}/classification/confirm", json={"product_ids": [p["id"]], "category_id": cat})
    assert r.json()["changed"] == 0  # a foreign product id is ignored


@pytest.mark.perf
def test_five_thousand_products(app, org):
    import uuid as _uuid
    from mla_api.models import Product
    api, o = org
    org_id = _uuid.UUID(o.rsplit("/", 1)[1])
    names = ["Pastilha de freio dianteira", "Filtro de óleo", "Camiseta manga curta", "Produto genérico"]
    with app.state.sessionmaker() as db:
        db.add_all(Product(organization_id=org_id, sku=f"P{i}", name=f"{names[i % 4]} {i}", description="", stock=1)
                   for i in range(5000))
        db.commit()
    t0 = time.perf_counter()
    totals = api.post(f"{o}/classification/run", json={}).json()
    elapsed = time.perf_counter() - t0
    assert totals["alta"] == 3750 and totals["baixa"] == 1250
    print(f"\n[perf] 5000 products classified in {elapsed:.1f}s (SQLite)")
    assert elapsed < 120
