"""Template Inspector + Validation Engine units (synthetic fixtures; see synthetic_template.py)."""
from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import date

import pytest
from synthetic_template import build

from mla_api.domain import template_inspector as ti
from mla_api.domain.listing_rules import (ProductData, TemplateContext, VariantData, batch_size_issue, photo_cell,
                                          preview_rows, suggest_source, validate_product, validate_template)

TODAY = date(2026, 11, 1)
MLSTATIC = "https://http2.mlstatic.com/D_NQ_NP_903478-MLM72199717417_102023-F.jpg"


def test_inspector_reports_structure_without_touching_the_file():
    data = build()
    before = hashlib.sha256(data).hexdigest()
    r = ti.inspect_workbook(data, today=TODAY)
    assert hashlib.sha256(data).hexdigest() == before
    assert r["help_sheet"] == "Ajuda"
    assert r["hidden_sheets"] == ["listas"]
    sheet = next(s for s in r["sheets"] if s["name"] == "Biscoitos")
    keys = {(m["key"], m["cell"]) for m in sheet["markers"]}
    assert {("required", "B4"), ("required", "G4"), ("error_summary", "H3"), ("catalog_code", "A3"),
            ("photos", "G3"), ("catalog_optional_note", "E5")} <= keys
    assert sheet["header_candidates"][0]["row"] == 3 or any(c["row"] == 3 for c in sheet["header_candidates"])
    assert sheet["formula_cells"] == 1
    assert sheet["data_validations"][0]["type"] == "list"
    assert sheet["preview"][2][:3] == ["Código do catálogo ML", "Título", "SKU"]


def test_deadline_found_with_inferred_year():
    r = ti.inspect_workbook(build(), today=TODAY)
    assert r["deadline"]["cell"] == "A6" and r["deadline"]["sheet"] == "Ajuda"
    assert r["deadline"]["date"] == "2026-09-10" and r["deadline"]["year_inferred"] is True


@pytest.mark.parametrize("text,ref,expected,inferred", [
    ("Faça isso até 10 de setembro", date(2026, 8, 1), "2026-09-10", True),
    ("Faça isso até 10 de setembro", date(2026, 11, 1), "2026-09-10", True),
    ("Faça isso até 5 de janeiro", date(2026, 12, 20), "2027-01-05", True),
    ("Envie até 3 de março de 2027", date(2026, 11, 1), "2027-03-03", False),
])
def test_deadline_parsing(text, ref, expected, inferred):
    found = ti.find_deadline(text, ref)
    assert found["date"] == expected and found["year_inferred"] is inferred


def test_no_help_sheet_is_reported_not_invented():
    r = ti.inspect_workbook(build(with_help=False), today=TODAY)
    assert r["help_sheet"] is None and r["deadline"] is None
    assert any("Ajuda" in w for w in r["warnings"])


def test_columns_of_confirmed_header_row():
    r = ti.inspect_workbook(build(), today=TODAY)
    cols = ti.sheet_columns(r, "Biscoitos", 3)
    assert [c["col"] for c in cols] == list("ABCDEFGH")
    assert {c["header"] for c in cols if c["required"]} == {"Título", "Preço", "Fotos"}


@pytest.mark.parametrize("data,msg", [
    (b"not a zip", "XLSX"),
    (b"PK\x03\x04garbage", "corrompido"),
])
def test_unsafe_or_broken_files_rejected(data, msg):
    with pytest.raises(ti.TemplateRejected, match=msg):
        ti.inspect_workbook(data, today=TODAY)


def test_zip_bomb_guard(monkeypatch):
    monkeypatch.setattr(ti, "MAX_UNCOMPRESSED_BYTES", 1000)
    with pytest.raises(ti.TemplateRejected, match="grande demais"):
        ti.inspect_workbook(build(), today=TODAY)


def test_macros_are_flagged_not_loaded():
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(build())) as src, zipfile.ZipFile(buf, "w") as dst:
        for item in src.infolist():
            dst.writestr(item, src.read(item))
        dst.writestr("xl/vbaProject.bin", b"\x00" * 10)
    r = ti.inspect_workbook(buf.getvalue(), today=TODAY)
    assert any("macros" in w for w in r["warnings"])


# --- validation engine ------------------------------------------------------------------------------------------
def product(**kw) -> ProductData:
    base = dict(id="1", sku="P1", name="Biscoito", brand="X", price_cents=500, stock=3, description="d",
                photo_urls=[MLSTATIC])
    base.update(kw)
    return ProductData(**base)


def codes(issues):
    return {i.code: (i.severity, i.source) for i in issues}


def test_complete_product_has_no_errors_or_warnings():
    assert [i for i in validate_product(product()) if i.severity != "info"] == []


def test_sources_are_never_mixed():
    issues = codes(validate_product(product(price_cents=None, photo_urls=[], gtin="7891234567890")))
    assert issues["price_missing"] == ("error", "interna")
    assert issues["photos_missing"] == ("warning", "documentacao")
    assert issues["gtin_invalid"] == ("warning", "interna")


def test_photo_rules():
    many = [f"https://http2.mlstatic.com/{n}.jpg" for n in range(11)]
    assert codes(validate_product(product(photo_urls=many)))["photos_over_group_limit"] == ("warning", "documentacao")
    assert codes(validate_product(product(photo_urls=["http://x.com/a.jpg"])))["photo_url_invalid"][0] == "error"
    assert codes(validate_product(product(photo_urls=["https://cdn.example.com/a.jpg"])))["photo_url_external"] == \
        ("warning", "hipotese")
    assert photo_cell([MLSTATIC, " https://http2.mlstatic.com/b.jpg "]) == MLSTATIC + ",https://http2.mlstatic.com/b.jpg"


def test_catalog_code_relaxes_photo_and_brand_rules():
    issues = codes(validate_product(product(photo_urls=[], brand="", catalog_code="MLB123")))
    assert issues["photos_missing"][0] == "info" and "brand_missing" not in issues
    assert "catalog_profile" in issues


def test_variation_rules():
    v = [VariantData("V1", {"Cor": "Azul"}), VariantData("V2", {"cor": "azul"}), VariantData("V3", {}),
         VariantData("V4", {"Tamanho": "M"})]
    issues = validate_product(product(variants=v))
    by = {(i.code, i.sku) for i in issues}
    assert ("variant_duplicate", "V2") in by and ("variant_no_attributes", "V3") in by
    assert ("variant_inconsistent", "V4") in by


def test_template_rules():
    assert codes(validate_template(None, TODAY))["template_missing"][0] == "error"
    expired = TemplateContext(deadline=date(2026, 9, 10), columns=[{"col": "B", "header": "Título", "required": True}])
    c = codes(validate_template(expired, TODAY))
    assert c["template_expired"] == ("error", "documentacao") and c["required_unmapped"] == ("error", "template")
    ok = TemplateContext(deadline=date(2026, 12, 1), deadline_confirmed=True,
                         columns=[{"col": "B", "header": "Título", "required": True}],
                         rules={"B": {"source": "name"}})
    assert validate_template(ok, TODAY) == []


def test_daily_limit():
    assert batch_size_issue(10_000) is None
    assert batch_size_issue(10_001).severity == "error"


def test_suggestions_and_preview_one_row_per_variation():
    assert suggest_source("Código do catálogo ML") == "catalog_code"
    assert suggest_source("Fotos") == "photos" and suggest_source("Resumo de erros") is None
    t = TemplateContext(columns=[{"col": "B", "header": "Título", "required": True},
                                 {"col": "C", "header": "SKU", "required": False},
                                 {"col": "D", "header": "Preço", "required": True},
                                 {"col": "I", "header": "Cor", "required": False},
                                 {"col": "J", "header": "Condição", "required": False}],
                        rules={"B": {"source": "name"}, "C": {"source": "sku"}, "D": {"source": "price"},
                               "I": {"source": "attr:Cor"}, "J": {"source": None, "default": "Novo"}})
    p = product(variants=[VariantData("V1", {"Cor": "Azul"}, price_cents=650), VariantData("V2", {"Cor": "Rosa"})])
    rows = preview_rows([p], t)
    assert [r["values"]["C"] for r in rows] == ["V1", "V2"]
    assert [r["values"]["D"] for r in rows] == ["6.50", "5.00"]
    assert [r["values"]["I"] for r in rows] == ["Azul", "Rosa"]
    assert rows[0]["values"]["J"] == "Novo" and rows[0]["values"]["B"] == "Biscoito"
