"""Central de Importações through the API, fictitious data only."""
from __future__ import annotations

import io
import json
import time

import pytest
from openpyxl import Workbook

CSV = ("Código interno;Nome do produto;EAN;Marca;Preço;Saldo;Cor;Produto pai;Imagens;Material\n"
       "FO-001;Filtro de óleo PSL55;07891234567895;Tecfil;25,90;40;;;https://exemplo.com/fo.jpg;Papel\n"
       "VL-002;Vela de ignição;;NGK;18,50;120;;;;\n"
       "VL-002;Vela repetida;;NGK;18,50;1;;;;\n"
       "CAM-1-AZ;Camiseta azul;;;;5;Azul;CAM-1;;\n"
       ";Sem SKU;;;;;;;;\n")


@pytest.fixture
def org(api):
    api.register("imp@example.com", org="Importadora Demo")
    return api, f"/api/orgs/{api.org_id()}"


def upload(api, o, name, data):
    return api.post(f"{o}/imports", files={"file": (name, data, "application/octet-stream")})


def mapping_from(analysis):
    return {s["column"]: s["field"] for s in analysis["suggestions"]}


def test_csv_analysis_suggestions_and_plan(org):
    api, o = org
    api.post(f"{o}/products", json={"sku": "CAM-1", "name": "Camiseta"})
    a = upload(api, o, "base.csv", CSV.encode("cp1252"))
    assert a.status_code == 201, a.text
    a = a.json()
    m = mapping_from(a)
    assert m["Código interno"] == "sku" and m["EAN"] == "gtin" and m["Saldo"] == "stock"
    assert m["Produto pai"] == "parent_sku" and a["preview"][0]["values"]["EAN"] == "07891234567895"
    m["Material"] = "attr"
    plan = api.post(f"{o}/imports/{a['job']['id']}/plan", json={"mapping": m}).json()
    t = plan["totals"]["plan"]
    assert (t["rows"], t["create"], t["variant"], t["error"]) == (5, 2, 1, 2)  # repeated SKU + missing SKU
    assert api.get(f"{o}/products").json()["total"] == 1  # dry run wrote nothing

    run = api.post(f"{o}/imports/{a['job']['id']}/run")
    assert run.status_code == 202
    job = api.get(f"{o}/imports").json()[0]
    assert job["status"] == "done" and job["totals"]["result"]["created"] == 2
    assert job["totals"]["result"]["variants"] == 1 and job["totals"]["result"]["errors"] == 2
    items = {p["sku"]: p for p in api.get(f"{o}/products", params={"limit": 50}).json()["items"]}
    fo = items["FO-001"]
    assert fo["gtin"] == "07891234567895" and fo["price_cents"] == 2590 and fo["stock"] == 40
    assert fo["attributes"]["Material"] == "Papel"
    assert fo["attributes"]["Imagens da base (URLs externas)"] == "https://exemplo.com/fo.jpg"
    cam = items["CAM-1"]
    assert api.get(f"{o}/products/{cam['id']}/variants").json()[0]["attributes"] == {"Cor": "Azul"}


def test_existing_skus_skipped_unless_update_confirmed(org):
    api, o = org
    p = api.post(f"{o}/products", json={"sku": "FO-001", "name": "Nome antigo", "brand": "Antiga",
                                        "description": "manter"}).json()
    data = "SKU;Nome;Marca\nFO-001;Nome novo;\n".encode()
    a = upload(api, o, "b.csv", data).json()
    m = {"SKU": "sku", "Nome": "internal_name", "Marca": "brand"}
    plan = api.post(f"{o}/imports/{a['job']['id']}/plan", json={"mapping": m}).json()
    assert plan["totals"]["plan"]["skip"] == 1
    plan = api.post(f"{o}/imports/{a['job']['id']}/plan", json={"mapping": m, "update_existing": True}).json()
    assert plan["totals"]["plan"]["update"] == 1 and plan["report"][0]["changes"] == ["name"]
    api.post(f"{o}/imports/{a['job']['id']}/run")
    after = api.get(f"{o}/products/{p['id']}").json()
    # Only the filled, different field changed; empty cells never erase data.
    assert (after["name"], after["brand"], after["description"]) == ("Nome novo", "Antiga", "manter")


def test_xlsx_json_xml(org):
    api, o = org
    wb = Workbook()
    ws = wb.active
    ws.append(["SKU", "Descrição", "Preço de venda", "Estoque"])
    ws.append(["X-1", "Produto planilha", 12.5, 3])
    buf = io.BytesIO()
    wb.save(buf)
    files = {
        "base.xlsx": buf.getvalue(),
        "base.json": json.dumps({"produtos": [{"sku": "J-1", "nome": "Produto JSON", "preco": "9,90"}]}).encode(),
        "base.xml": b"<produtos><produto><sku>XM-1</sku><nome>Produto XML</nome></produto></produtos>",
    }
    for name, data in files.items():
        a = upload(api, o, name, data)
        assert a.status_code == 201, (name, a.text)
        a = a.json()
        m = mapping_from(a)
        assert "sku" in m.values(), (name, m)
        plan = api.post(f"{o}/imports/{a['job']['id']}/plan", json={"mapping": m}).json()
        assert plan["totals"]["plan"]["create"] == 1, (name, plan["report"])
        api.post(f"{o}/imports/{a['job']['id']}/run")
    skus = {p["sku"] for p in api.get(f"{o}/products").json()["items"]}
    assert {"X-1", "J-1", "XM-1"} <= skus


def test_refusals(org):
    api, o = org
    assert upload(api, o, "x.pdf", b"%PDF-1.4").status_code == 415
    assert upload(api, o, "x.exe", b"MZ").status_code == 415
    a = upload(api, o, "x.csv", "A;B\n1;2\n".encode()).json()
    r = api.post(f"{o}/imports/{a['job']['id']}/plan", json={"mapping": {"A": "internal_name"}})
    assert r.status_code == 422 and "SKU" in r.json()["detail"]
    r = api.post(f"{o}/imports/{a['job']['id']}/plan", json={"mapping": {"A": "sku", "Z": "brand"}})
    assert r.status_code == 422
    r = api.post(f"{o}/imports/{a['job']['id']}/plan", json={"mapping": {"A": "sku", "B": "__class__"}})
    assert r.status_code == 422
    assert api.post(f"{o}/imports/{a['job']['id']}/run").status_code == 409  # must plan first
    assert api.post(f"{o}/imports/{a['job']['id']}/cancel").json()["status"] == "cancelled"


def test_profiles_and_isolation(org, new_api):
    api, o = org
    assert api.post(f"{o}/import-profiles", json={"name": "ERP X", "mapping": {"Código": "sku"}}).status_code == 201
    assert api.post(f"{o}/import-profiles", json={"name": "ERP X", "mapping": {"Código": "sku", "N": "internal_name"}}).status_code == 201
    assert len(api.get(f"{o}/import-profiles").json()) == 1
    a = upload(api, o, "x.csv", "SKU;Nome\nA;B\n".encode()).json()
    other = new_api()
    other.register("other@example.com", org="Outra")
    o2 = f"/api/orgs/{other.org_id()}"
    assert other.get(f"{o}/imports").status_code == 404
    assert other.get(f"{o2}/imports/{a['job']['id']}").status_code == 404
    assert other.post(f"{o2}/imports/{a['job']['id']}/run").status_code == 404
    assert other.get(f"{o2}/import-profiles").json() == []


@pytest.mark.perf
def test_thousand_rows(org):
    api, o = org
    lines = ["SKU;Nome;Preço;Estoque"] + [f"P{i:05d};Produto {i};{10 + i % 50},90;{i % 7}" for i in range(1000)]
    a = upload(api, o, "mil.csv", "\n".join(lines).encode()).json()
    m = mapping_from(a)
    t0 = time.perf_counter()
    plan = api.post(f"{o}/imports/{a['job']['id']}/plan", json={"mapping": m}).json()
    api.post(f"{o}/imports/{a['job']['id']}/run")
    elapsed = time.perf_counter() - t0
    assert plan["totals"]["plan"]["create"] == 1000
    assert api.get(f"{o}/products").json()["total"] == 1000
    assert api.get(f"{o}/products", params={"q": "P00007"}).json()["items"][0]["sku"] == "P00007"  # zeros kept
    print(f"\n[perf] 1000 rows planned + imported in {elapsed:.1f}s (SQLite)")
    assert elapsed < 60
