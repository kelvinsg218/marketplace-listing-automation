"""End-to-end through the API with a synthetic official-like file and fictitious products."""
from __future__ import annotations

import io

import pytest
from openpyxl import load_workbook
from synthetic_template import build_official_like

SHEET = "Peças de Teste"
URL = "https://http2.mlstatic.com/D_NQ_NP_000000-MLA00000000000_000000-F.jpg"


@pytest.fixture
def ready(api):
    api.register("ops@example.com", org="Peças Demo")
    org = api.org_id()
    o = f"/api/orgs/{org}"
    acc = api.post(f"{o}/seller-accounts", json={"label": "Conta teste"}).json()
    tpl = api.post(f"{o}/templates", data={"seller_account_id": acc["id"], "source": "categories"},
                   files={"file": ("oficial-sintetico.xlsx", build_official_like(), "application/octet-stream")}).json()
    assert tpl["deadline_confirmed"] is True and tpl["deadline_date"] == "2099-12-01"
    m = api.get(f"{o}/templates/{tpl['id']}/mapping", params={"sheet": SHEET}).json()
    assert m["header_row"] == 3
    cond = next(c for c in m["columns"] if c["header"] == "Condição")
    assert cond["options"] == ["Novo", "Usado"] and cond["strict"] is True
    rules = {"A": {"source": "name"}, "D": {"source": "photos"}, "E": {"source": "sku"}, "F": {"source": "stock"},
             "G": {"source": "price"}, "L": {"source": "brand"}, "M": {"source": "attr:Número de peça"}}
    assert api.put(f"{o}/templates/{tpl['id']}/mapping",
                   json={"sheet_name": SHEET, "header_row": 3, "rules": rules}).status_code == 200
    p = api.add_product(org, "CM-1", price_cents=19990, stock=4, brand="",
                        attributes={"Número de peça": "CM-001", "Fabricante": "Fábrica Fictícia"})
    api.post(f"{o}/products/{p['id']}/images", json=[{"official_url": URL}])
    b = api.post(f"{o}/batches", json={"name": "Lote teste"}).json()
    url = f"{o}/batches/{b['id']}"
    api.patch(url, json={"seller_account_id": acc["id"]})
    api.patch(url, json={"template_id": tpl["id"], "sheet_name": SHEET})
    api.put(f"{url}/items", json={"product_ids": [p["id"]]})
    return api, org, o, url, b, p, tpl


def test_export_blocked_until_fixed_then_generated(ready):
    api, org, o, url, b, p, tpl = ready
    v = api.post(f"{url}/validate").json()
    assert v["summary"]["writer_available"] is True and v["summary"]["ready"] is False
    issue = next(i for i in v["products"][0]["issues"] if i["code"] == "template_required")
    assert issue["field"] == "L" and issue["source"] == "template"  # Marca is required by the file
    assert api.post(f"{url}/export").status_code == 409

    # Assistente de Correção: the error summary points at "Marca"; a sentence becomes a proposal.
    es = api.post(f"{url}/error-summary", json={"text": "- Marca\n- Coisa desconhecida"}).json()
    assert es["items"][0]["column"] == "Marca" and es["items"][1]["column"] is None
    prop = api.post(f"{o}/rules/interpret", json={
        "batch_id": b["id"], "text": "Daqui para frente use o fabricante cadastrado no campo Marca quando estiver vazio"}).json()
    assert prop["definition"]["params"] == {"field": "attr:Fabricante"} and prop["scope"] == "category"
    assert prop["simulation"]["rows"][0] == {"sku": "CM-1", "before": "", "after": "Fábrica Fictícia", "changed": True}
    body = {"batch_id": b["id"], "definition": prop["definition"], "scope": "category", "scope_ref": SHEET,
            "name": "Marca a partir do fabricante", "origin": "prompt", "origin_text": "teste"}
    assert api.post(f"{o}/rules", json=body).status_code == 409          # needs explicit approval
    rule = api.post(f"{o}/rules", json={**body, "approved": True}).json()
    assert rule["version"] == 1 and rule["scope_ref"] == SHEET

    v = api.post(f"{url}/validate").json()
    assert v["summary"]["ready"] is True, [(i["code"], i["field"], i["message"]) for i in v["products"][0]["issues"]
                                           + v["template_issues"] + v["batch_issues"] if i["severity"] == "error"]
    prev = api.get(f"{url}/preview").json()
    assert prev["first_row"] == 7 and prev["rows"][0]["values"]["L"] == "Fábrica Fictícia"
    assert prev["rows"][0]["rules"][0][0] == rule["id"]

    exp = api.post(f"{url}/export")
    assert exp.status_code == 201, exp.text
    e = exp.json()
    assert e["rows"] == 1 and e["checks"]["integrity"] == "ok" and e["rules_applied"] == [[rule["id"], 1]]
    assert api.get(url).json()["status"] == "exported"
    f = api.get(f"{url}/exports/{e['id']}/file")
    assert f.status_code == 200 and "attachment" in f.headers["content-disposition"]
    ws = load_workbook(io.BytesIO(f.content))[SHEET]
    assert [ws["A7"].value, ws["D7"].value, ws["G7"].value, ws["L7"].value, ws["M7"].value] == \
        ["Produto CM-1", URL, 199.9, "Fábrica Fictícia", "CM-001"]
    # Sending is still the user's explicit step; it is now possible because a file exists.
    assert api.post(f"{url}/confirm-sent", json={"note": "enviado"}).json()["status"] == "sent_external"
    assert api.post(f"{url}/export").status_code == 409  # sent batches are locked


def test_rule_versions_revert_and_official_conflict(ready):
    api, org, o, url, b, p, tpl = ready
    base = {"batch_id": b["id"], "scope": "batch", "name": "Condição", "approved": True}
    bad = api.post(f"{o}/rules", json={**base, "definition": {"target": "Condição", "operation": "set_value",
                                                               "params": {"value": "Seminovo"}}})
    assert bad.status_code == 409 and "lista oficial" in bad.json()["detail"]
    r = api.post(f"{o}/rules", json={**base, "definition": {"target": "Condição", "operation": "set_value",
                                                             "params": {"value": "Usado"}}}).json()
    v2 = api.patch(f"{o}/rules/{r['id']}", json={"definition": {"target": "Condição", "operation": "set_value",
                                                                 "params": {"value": "Novo"}}, "note": "ajuste"}).json()
    assert v2["version"] == 2
    v3 = api.post(f"{o}/rules/{r['id']}/revert", json={"version": 1}).json()
    assert v3["version"] == 3 and v3["definition"]["params"] == {"value": "Usado"}
    hist = api.get(f"{o}/rules/{r['id']}/versions").json()
    assert [h["version"] for h in hist] == [3, 2, 1] and hist[0]["note"] == "reversão para v1"
    assert api.patch(f"{o}/rules/{r['id']}", json={"status": "inactive"}).json()["status"] == "inactive"
    bogus = api.post(f"{o}/rules/simulate", json={"batch_id": b["id"], "definition": {
        "target": "Marca", "operation": "exec", "params": {"code": "1"}}})
    assert bogus.status_code == 422


def test_rules_and_exports_are_isolated(ready, new_api):
    api, org, o, url, b, p, tpl = ready
    r = api.post(f"{o}/rules", json={"batch_id": b["id"], "scope": "organization", "name": "x", "approved": True,
                                     "definition": {"target": "Marca", "operation": "default_if_empty",
                                                    "params": {"value": "Genérica"}}}).json()
    exp = api.post(f"{url}/export").json()
    other = new_api()
    other.register("other@example.com", org="Outra")
    org_b = other.org_id()
    for path in [f"{o}/rules", f"{o}/rules/{r['id']}/versions", f"{url}/exports", f"{url}/exports/{exp['id']}/file"]:
        assert other.get(path).status_code == 404
    # Through their own organization, foreign ids are invisible and foreign scopes refused.
    assert other.get(f"/api/orgs/{org_b}/rules").json() == []
    assert other.patch(f"/api/orgs/{org_b}/rules/{r['id']}", json={"status": "inactive"}).status_code == 404
    assert other.post(f"/api/orgs/{org_b}/rules/simulate", json={"batch_id": b["id"], "definition": {
        "target": "Marca", "operation": "set_value", "params": {"value": "x"}}}).status_code == 404
