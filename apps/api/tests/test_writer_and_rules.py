"""Official Writer, inspector v2 and adaptive rules. Synthetic files mirror the real layout; the optional test at the
end runs on a sanitized copy of a real template when it exists locally (never committed)."""
from __future__ import annotations

import io
import re
import zipfile
from datetime import date
from pathlib import Path

import pytest
from openpyxl import load_workbook
from synthetic_template import build_official_like

from mla_api.domain import adaptive_rules as ar
from mla_api.domain import template_inspector as ti
from mla_api.domain import workbook_writer as ww
from mla_api.domain.listing_rules import SOURCE_FIELDS, ProductData, VariantData
from mla_api.domain.sheet_builder import build_rows, validate_rows

TODAY = date(2026, 11, 1)
SHEET = "Peças de Teste"
URL = "https://http2.mlstatic.com/D_NQ_NP_000000-MLA00000000000_000000-F.jpg"
REAL_SANITIZED = Path(__file__).parents[3] / "docs" / "ml-research" / "sanitized" / "template-sanitizado.xlsx"


@pytest.fixture(scope="module")
def official():
    data = build_official_like()
    report = ti.inspect_workbook(data, today=TODAY)
    layout = next(s for s in report["sheets"] if s["name"] == SHEET)["layout"]
    return data, report, layout


# --- inspector v2 ----------------------------------------------------------------------------------------------
def test_layout_read_from_the_file(official):
    _, report, layout = official
    assert (layout["header_row"], layout["data_start_row"], layout["capacity"]) == (3, 7, 20)
    cols = {c["header"]: c for c in layout["columns"]}
    assert cols["Condição"]["options"] == ["Novo", "Usado"] and cols["Condição"]["strict"] is True
    assert cols["Varia por: Tamanho"]["strict"] is False
    assert cols["Preço [R$]"]["min_value"] == 8.0 and cols["Preço [R$]"]["required"]
    assert cols["Título: informe o produto, marca, modelo e destaque as características principais"]["max_length"] == 60
    assert cols["BUYBOX_FORMULA"]["helper"] and not cols["BUYBOX_FORMULA"]["writable"]
    assert not cols["Quantidade de caracteres"]["writable"] and cols["Fotos"]["writable"]
    assert cols["Condição"]["default"] == "Novo"
    assert layout["variation_columns"] == ["K"]
    # Deadline "antes de 1 de dezembro" + technical date in the hidden sheet: year confirmed, not guessed.
    assert report["deadline"]["date"] == "2099-12-01" and report["deadline"]["year_inferred"] is False
    # Hidden sheets are never previewed (they hold the account binding in real files).
    assert next(s for s in report["sheets"] if s["name"] == "extra info")["preview"] == []


def test_compare_reports_detects_breaking_changes(official):
    _, report, _ = official
    changed = ti.inspect_workbook(build_official_like(rows=25), today=TODAY)
    for s in changed["sheets"]:
        if s["name"] == SHEET:
            s["layout"]["columns"] = [c for c in s["layout"]["columns"] if c["header"] != "Marca"]
            next(c for c in s["layout"]["columns"] if c["header"] == "SKU")["required"] = True
    d = ti.compare_reports(report, changed)
    assert d["sheets"][SHEET]["columns_removed"] == ["Marca"]
    assert d["sheets"][SHEET]["became_required"] == ["SKU"]
    assert d["breaking"] is True
    assert ti.compare_reports(report, report)["breaking"] is False


# --- writer -----------------------------------------------------------------------------------------------------
def test_writer_changes_only_data_cells(official):
    data, _, layout = official
    rows = [{"A": "Cilindro mestre teste", "D": URL, "F": 3, "G": "199.90", "L": "Marca Fictícia", "M": "CMF-1"},
            {"A": "Pastilha teste", "D": URL, "F": 0, "G": "89.5", "L": "Marca Fictícia", "M": "PT-2", "K": "M"}]
    res = ww.fill(data, SHEET, layout, rows)
    assert ww.verify(data, res.data, res.sheet_part) == []
    a, b = zipfile.ZipFile(io.BytesIO(data)), zipfile.ZipFile(io.BytesIO(res.data))
    assert a.namelist() == b.namelist()
    changed = [n for n in a.namelist() if a.read(n) != b.read(n)]
    assert res.sheet_part in changed and set(changed) <= {res.sheet_part, "xl/workbook.xml"}
    assert 'fullCalcOnLoad="1"' in b.read("xl/workbook.xml").decode()
    sa, sb = a.read(res.sheet_part).decode(), b.read(res.sheet_part).decode()
    assert sa.count("<f>") == sb.count("<f>")  # every formula kept
    wb = load_workbook(io.BytesIO(res.data))
    ws = wb[SHEET]
    assert [ws["A7"].value, ws["D7"].value, ws["F7"].value, ws["G7"].value] == ["Cilindro mestre teste", URL, 3, 199.9]
    assert ws["C7"].value == "Novo" and ws["I7"].value == "Clássico"  # template defaults kept
    assert ws["K8"].value == "M" and ws["K7"].value == "Insira ou selecione um valor"
    assert ws["B7"].value.startswith("=LEN(") and ws["N7"].value.startswith("=IF(")
    assert ws["A3"].value.startswith("Título") and ws["A4"].value == "Obrigatório"  # header rows untouched
    assert ws["A9"].value is None  # rows after the batch untouched
    assert wb["extra info"].sheet_state == "veryHidden"


def test_writer_escapes_text_and_refuses_non_input_columns(official):
    data, _, layout = official
    res = ww.fill(data, SHEET, layout, [{"A": 'Peça <b>&"teste"</b>', "L": "=CMD()"}])
    ws = load_workbook(io.BytesIO(res.data))[SHEET]
    assert ws["A7"].value == 'Peça <b>&"teste"</b>'
    assert ws["L7"].data_type == "s"  # written as text, never as a formula
    with pytest.raises(ww.WriterError, match="não é um campo"):
        ww.fill(data, SHEET, layout, [{"N": "TRUE"}])  # helper column
    with pytest.raises(ww.WriterError, match="não é um campo"):
        ww.fill(data, SHEET, layout, [{"B": "99"}])  # computed column
    with pytest.raises(ww.WriterError, match="comporta 20"):
        ww.fill(data, SHEET, layout, [{"A": "x"}] * 21)
    with pytest.raises(ww.WriterError, match="Aba não encontrada"):
        ww.fill(data, "Outra", layout, [{"A": "x"}])


# --- builder + template validation ------------------------------------------------------------------------------
def product(**kw) -> ProductData:
    base = dict(id="p1", sku="P1", name="Cilindro mestre", brand="Marca X", price_cents=19990, stock=3,
                photo_urls=[URL], attributes={"Número de peça": "CM-1", "Fabricante": "Fábrica Y"})
    base.update(kw)
    return ProductData(**base)


MAPPING = {"A": {"source": "name"}, "D": {"source": "photos"}, "E": {"source": "sku"}, "F": {"source": "stock"},
           "G": {"source": "price"}, "L": {"source": "brand"}, "M": {"source": "attr:Número de peça"}}


def test_complete_product_has_no_template_errors(official):
    _, _, layout = official
    rows = build_rows([product()], layout, MAPPING, [])
    validate_rows(rows, layout, [product()])
    assert [i for i in rows[0].issues if i.severity == "error"] == []
    assert rows[0].values["G"] == "199.90" and rows[0].final["C"] == "Novo"


def test_template_requirements(official):
    _, _, layout = official
    p = product(brand="", price_cents=500, name="X" * 70, variants=[
        VariantData("V1", {"Tamanho": "P"}, price_cents=19990), VariantData("V2", {"Tamanho": "M"}, price_cents=20990)])
    rows = build_rows([p], layout, {**MAPPING, "C": {"source": None, "default": "Seminovo"}}, [])
    validate_rows(rows, layout, [p])
    codes = {(i.code, i.field) for i in rows[0].issues}
    assert ("template_required", "L") in codes                # Marca empty, required
    assert ("template_list", "C") in codes                     # not in the strict official list
    assert ("template_length", "A") in codes                   # > 60 characters
    assert ("variation_mismatch", "G") in codes                # variations with different prices
    assert [r.values["K"] for r in rows] == ["P", "M"]         # "Varia por: Tamanho" <- variation attribute
    assert all(i.source == "template" for i in rows[0].issues if i.code.startswith(("template", "variation")))


# --- adaptive rules ---------------------------------------------------------------------------------------------
def rule(target, op, params=None, when="always", scope="organization", priority=100, rid="r"):
    d = ar.validate_definition({"target": target, "operation": op, "params": params or {},
                                "condition": {"when": when}}, set(SOURCE_FIELDS))
    return ar.ActiveRule(rid, 1, scope, priority, d)


@pytest.mark.parametrize("raw,msg", [
    ({"target": "Marca", "operation": "exec", "params": {"code": "import os"}}, "não permitida"),
    ({"target": "Marca", "operation": "copy_field", "params": {"field": "__import__('os')"}}, "desconhecido"),
    ({"target": "Marca", "operation": "set_value", "params": {"value": "x", "sql": "drop table"}}, "não permitidos"),
    ({"target": "Marca", "operation": "truncate", "params": {"length": "9; rm -rf"}}, "limite"),
    ({"target": "Marca", "operation": "normalize", "params": {"mode": "eval"}}, "Modo"),
    ({"target": "Marca", "operation": "set_value", "params": {"value": "x"}, "condition": {"when": "python"}},
     "Condição"),
])
def test_rule_schema_is_closed(raw, msg):
    with pytest.raises(ar.RuleInvalid, match=msg):
        ar.validate_definition(raw, set(SOURCE_FIELDS))


def test_rule_precedence_and_operations(official):
    _, _, layout = official
    p = product(brand="")
    rules = [rule("Marca", "copy_field", {"field": "attr:Fabricante"}, when="target_empty", rid="org"),
             rule("Marca", "normalize", {"mode": "upper"}, scope="batch", rid="lote"),
             rule("Número de peça", "prefix", {"value": "REF-"}, scope="category", rid="cat")]
    row = build_rows([p], layout, MAPPING, rules)[0]
    assert row.values["L"] == "FÁBRICA Y" and row.values["M"] == "REF-CM-1"
    assert {a[0] for a in row.applied} == {"org", "lote", "cat"}
    # A more specific scope wins over a broader one for the same column.
    rules = [rule("Marca", "set_value", {"value": "Batch"}, scope="batch", rid="b"),
             rule("Marca", "set_value", {"value": "Org"}, scope="organization", rid="o")]
    assert build_rows([p], layout, MAPPING, rules)[0].values["L"] == "Batch"


def test_rules_cannot_break_official_requirements(official):
    _, _, layout = official
    specs = {c["header"]: c for c in layout["columns"]}
    d = rule("Condição", "set_value", {"value": "Seminovo"}).definition
    assert "não está na lista oficial" in ar.official_conflict(d, specs["Condição"])
    assert "calculada" in ar.official_conflict(rule("Quantidade de caracteres", "set_value", {"value": "1"}).definition,
                                               specs["Quantidade de caracteres"])
    assert "não existe" in ar.official_conflict(rule("Inexistente", "set_value", {"value": "1"}).definition, None)
    # Even if a rule produced an invalid value, validation after rules still blocks it.
    p = product()
    rows = build_rows([p], layout, MAPPING, [rule("Condição", "set_value", {"value": "Seminovo"})])
    validate_rows(rows, layout, [p])
    assert any(i.code == "template_list" for i in rows[0].issues)


def test_interpret_user_example():
    headers = ["Marca", "Número de peça", "Fotos", "Condição"]
    p = ar.interpret("O Mercado Livre recusou porque o campo de marca precisa estar preenchido com o fabricante. "
                     "Daqui para frente, use o fabricante cadastrado quando a marca estiver vazia.",
                     headers, ["Fabricante"])
    assert p.definition == {"target": "Marca", "operation": "copy_field", "params": {"field": "attr:Fabricante"},
                            "condition": {"when": "target_empty"}}
    assert p.scope == "category"
    q = ar.interpret('Somente neste lote, preencha o campo Condição com "Novo"', headers, [])
    assert q.definition["operation"] == "set_value" and q.definition["params"] == {"value": "Novo"}
    assert q.scope == "batch"
    vague = ar.interpret("arrume os erros", headers, [])
    assert vague.definition is None and vague.questions  # asks instead of guessing


def test_error_summary_parsing():
    items = ar.parse_error_summary("- Marca\n- Estoque\n- Forma de envio\n- Algo desconhecido",
                                   ["Marca", "Estoque", "Forma de envio"])
    assert [i["column"] for i in items] == ["Marca", "Estoque", "Forma de envio", None]


# --- sanitizer (tool) -------------------------------------------------------------------------------------------
def test_sanitizer_removes_binding(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("sanitize", Path(__file__).parents[1] / "tools" / "sanitize_template.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    original = build_official_like(fake_binding="9876543210-bulk-sell-0123456789ab")
    clean, counts = mod.sanitize(original)
    assert counts["values"] >= 2 and b"9876543210" not in clean
    assert all(b"9876543210" not in zipfile.ZipFile(io.BytesIO(clean)).read(n)
               for n in zipfile.ZipFile(io.BytesIO(clean)).namelist())


# --- optional: real structure (sanitized copy, local only) ------------------------------------------------------
@pytest.mark.skipif(not REAL_SANITIZED.exists(), reason="cópia sanitizada do template real não disponível")
def test_real_template_structure_and_writer():
    data = REAL_SANITIZED.read_bytes()
    report = ti.inspect_workbook(data, today=TODAY)
    assert report["deadline"]["year_inferred"] is False
    layouts = {s["name"]: s["layout"] for s in report["sheets"] if s["layout"] and s["layout"]["data_start_row"]}
    assert len(layouts) >= 1
    for name, layout in layouts.items():
        assert layout["header_row"] == 3 and layout["capacity"] > 900
        titles = [c for c in layout["columns"] if c["header"].startswith("Título")]
        rows = [{titles[0]["col"]: f"Produto fictício {i}"} for i in range(3)]
        res = ww.fill(data, name, layout, rows)
        assert ww.verify(data, res.data, res.sheet_part) == [], name
        b = zipfile.ZipFile(io.BytesIO(res.data))
        a = zipfile.ZipFile(io.BytesIO(data))
        assert len(re.findall(r"<f>", a.read(res.sheet_part).decode())) == \
            len(re.findall(r"<f>", b.read(res.sheet_part).decode()))
