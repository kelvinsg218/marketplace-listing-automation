"""Import center with a fictitious company base (Auto Peças Horizonte) in every supported format."""
import json
import threading
import zipfile

import pytest

from mla.core.enums import DataSource, ImportAction, ImportStatus, Verification
from mla.core.models import Product
from mla.importing.archive import extract_archive
from mla.importing.mapping import normalize_key, suggest_mapping
from mla.importing.readers import SourceError, detect_format, open_source
from mla.importing.service import ImportCancelled, ImportOptions, ImportProblem
from mla.persistence.repositories import ProductQuery
from conftest import make_png

CSV_HEADER = "codigo;descricao;preco_venda;saldo;marca;ean;foto\n"


def write(path, text, encoding="utf-8"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding)
    return path


def run_import(ctx, path, mapping=None, target="products", options=None, include_review=False):
    analysis = ctx.imports.analyze(path, target)
    batch = ctx.imports.plan(analysis, mapping or analysis.mapping(), options or ImportOptions())
    if include_review:
        ctx.imports.set_decision_for_action(batch.id, ImportAction.REVIEW, "create")
    report = ctx.imports.commit(batch.id)
    return analysis, batch, report


# ------------------------------------------------------------------ detection and readers
def test_detect_format_and_refusals(tmp_path):
    assert detect_format(write(tmp_path / "a.csv", "sku;nome\n1;x\n")) == "csv"
    assert detect_format(write(tmp_path / "a.json", '[{"sku": "1"}]')) == "json"
    assert detect_format(write(tmp_path / "a.xml", "<p><i><sku>1</sku></i></p>")) == "xml"
    with pytest.raises(SourceError, match="xls"):
        detect_format(write(tmp_path / "velho.xls", "x"))
    with pytest.raises(SourceError, match="não parece"):
        detect_format(write(tmp_path / "falso.xlsx", "sku;nome"))
    with pytest.raises(SourceError, match="vazio"):
        detect_format(write(tmp_path / "vazio.csv", ""))


def test_csv_windows_1252_and_suggestions(tmp_path):
    path = write(tmp_path / "base.csv", CSV_HEADER + "HZ-1;Filtro de óleo;29,90;10;Horizonte;;\n",
                 encoding="cp1252")
    source = open_source(path)
    assert "Windows-1252" in source.info.notes[0]
    row = source.preview()[0]
    assert row.values["descricao"] == "Filtro de óleo"
    suggestions = {s.column: s for s in suggest_mapping(source.info.headers, [row.values])}
    assert suggestions["codigo"].field == "sku" and suggestions["codigo"].needs_confirmation
    assert suggestions["descricao"].field == "internal_name"  # short text → name
    assert suggestions["preco_venda"].field == "price_cents" and not suggestions["preco_venda"].needs_confirmation
    assert suggestions["saldo"].field == "stock" and suggestions["saldo"].needs_confirmation
    assert suggestions["foto"].field == "images"
    assert normalize_key("Preço de Venda (R$)") == "preco_de_venda_r"


def test_long_description_maps_to_description():
    long_text = "Pastilha de freio cerâmica com indicador sonoro de desgaste e baixo nível de ruído"
    s = suggest_mapping(["descricao"], [{"descricao": long_text}])[0]
    assert s.field == "description"


def test_csv_extra_cells_flag_review(tmp_path):
    path = write(tmp_path / "x.csv", "sku;nome;preco\nA-1;Filtro; óleo;10\n")
    row = open_source(path).preview()[0]
    assert "deslocados" in row.review


# ------------------------------------------------------------------ CSV create + images + update
@pytest.fixture
def horizonte_csv(tmp_path):
    base = tmp_path / "cliente"
    make_png(base / "fotos" / "HZ-1001.png")
    make_png(base / "fotos" / "HZ-1001_2.png", color=(10, 200, 10))
    make_png(base / "imgs" / "pastilha.png", color=(200, 10, 10))
    text = (CSV_HEADER
            + "HZ-1001;Filtro de óleo;29,90;10;Horizonte;7891234567895;\n"
            + "HZ-1002;Pastilha de freio;119,00;4;Horizonte;;imgs/pastilha.png | sumida.jpg\n"
            + "HZ-1003;Vela de ignição;15,50;0;Horizonte;;https://exemplo.com/vela.jpg\n")
    return write(base / "produtos.csv", text)


def test_csv_import_creates_products_with_images_and_pending_media(ctx, horizonte_csv):
    analysis, batch, report = run_import(ctx, horizonte_csv)
    assert batch.counts["planned"] == {"create": 3}
    assert report.counts["created"] == 3 and report.counts["errors"] == 0
    filtro = ctx.products.get(ctx.products.id_for_sku("HZ-1001"))
    assert filtro.price_cents == 2990 and filtro.stock == 10 and filtro.gtin == "7891234567895"
    assert len(filtro.images) == 2, "found by SKU in the file name (main + _2)"
    assert {i.original_name for i in filtro.images} == {"HZ-1001.png", "HZ-1001_2.png"}
    assert filtro.source.startswith(f"Importação #{batch.id}")
    pastilha = ctx.products.get(ctx.products.id_for_sku("HZ-1002"))
    assert len(pastilha.images) == 1
    assert [m.reference for m in pastilha.missing_media] == ["sumida.jpg"]
    vela = ctx.products.get(ctx.products.id_for_sku("HZ-1003"))
    assert [m.reference for m in vela.missing_media] == ["https://exemplo.com/vela.jpg"]
    assert ctx.imports.get(batch.id).status is ImportStatus.COMPLETED


def test_update_changes_only_filled_fields_and_keeps_images(ctx, horizonte_csv, tmp_path):
    run_import(ctx, horizonte_csv)
    pid = ctx.products.id_for_sku("HZ-1001")
    product = ctx.products.get(pid)
    product.description = "Descrição escrita no MLA, não pode sumir."
    ctx.catalog.save(product)
    update = write(tmp_path / "precos.csv", "sku;preco;estoque;descricao_completa\nHZ-1001;31,50;;\nHZ-1002;119,00;4;\n")
    analysis = ctx.imports.analyze(update)
    batch = ctx.imports.plan(analysis, analysis.mapping(), ImportOptions(match_images_by_sku=False))
    rows = {r.sku: r for r in ctx.imports.rows(batch.id)}
    assert rows["HZ-1001"].action is ImportAction.UPDATE
    assert [(c["field"], c["old"], c["new"]) for c in rows["HZ-1001"].changes] == [
        ("price_cents", "R$ 29,90", "R$ 31,50")]
    assert rows["HZ-1002"].action is ImportAction.UNCHANGED and rows["HZ-1002"].decision == "skip"
    ctx.imports.commit(batch.id)
    after = ctx.products.get(pid)
    assert after.price_cents == 3150 and after.stock == 10
    assert after.description == "Descrição escrita no MLA, não pode sumir."
    assert len(after.images) == 2


def test_existing_skus_ignored_when_update_disabled(ctx, horizonte_csv, tmp_path):
    run_import(ctx, horizonte_csv)
    update = write(tmp_path / "p.csv", "sku;preco\nHZ-1001;99,00\n")
    analysis = ctx.imports.analyze(update)
    batch = ctx.imports.plan(analysis, analysis.mapping(), ImportOptions(update_existing=False))
    row = ctx.imports.rows(batch.id)[0]
    assert row.action is ImportAction.UPDATE and row.decision == "skip"
    ctx.imports.commit(batch.id)
    assert ctx.products.get(ctx.products.id_for_sku("HZ-1001")).price_cents == 2990


def test_user_edit_after_analysis_wins(ctx, horizonte_csv, tmp_path):
    run_import(ctx, horizonte_csv)
    update = write(tmp_path / "p.csv", "sku;preco;marca\nHZ-1001;35,00;Horizon\n")
    analysis = ctx.imports.analyze(update)
    batch = ctx.imports.plan(analysis, analysis.mapping())
    product = ctx.products.get(ctx.products.id_for_sku("HZ-1001"))
    product.price_cents = 4000  # edited in the app before confirming
    ctx.catalog.save(product)
    ctx.imports.commit(batch.id)
    after = ctx.products.get(product.id)
    assert after.price_cents == 4000 and after.brand == "Horizon"
    assert "mantido" in ctx.imports.rows(batch.id)[0].outcome


def test_duplicate_sku_in_file_and_errors_per_row(ctx, tmp_path):
    path = write(tmp_path / "d.csv", "sku;nome;preco;estoque;ean\n"
                                     "A-1;Um;10,00;1;\n"
                                     "A-1;Um de novo;11,00;1;\n"
                                     "A 2;Com espaço;10;1;\n"
                                     "A-3;Preço ruim;abc;1;\n"
                                     "A-4;Estoque quebrado;10;2,5;\n"
                                     "A-5;EAN cientifico;10;1;7,89123E+12\n"
                                     ";Sem SKU;10;1;\n")
    analysis = ctx.imports.analyze(path)
    batch = ctx.imports.plan(analysis, analysis.mapping())
    rows = {r.row_no: r for r in ctx.imports.rows(batch.id)}
    assert rows[1].action is ImportAction.CREATE
    assert rows[2].action is ImportAction.ERROR and "repetido" in rows[2].issues[0]["message"]
    assert "espaços" in rows[3].issues[0]["message"]
    assert "Preço de venda inválido" in rows[4].issues[0]["message"]
    assert "inteiro" in rows[5].issues[0]["message"]
    assert "notação científica" in rows[6].issues[0]["message"]
    assert "sem SKU" in rows[7].issues[0]["message"]
    report = ctx.imports.commit(batch.id)
    assert report.counts["created"] == 1 and report.counts["skipped"] == 6
    out = tmp_path / "relatorio.csv"
    assert ctx.imports.export_report(batch.id, out) == 7
    assert "notação científica" in out.read_text(encoding="utf-8-sig")


def test_mapping_requires_sku(ctx, horizonte_csv):
    analysis = ctx.imports.analyze(horizonte_csv)
    mapping = analysis.mapping()
    mapping["codigo"] = ""
    with pytest.raises(ImportProblem, match="SKU"):
        ctx.imports.plan(analysis, mapping)


# ------------------------------------------------------------------ XLSX / JSON / XML / PDF
def test_xlsx_numbers_and_sheet(ctx, tmp_path):
    from openpyxl import Workbook
    wb = Workbook()
    wb.active.title = "Capa"
    wb.active["A1"] = "Catálogo fictício"
    ws = wb.create_sheet("Produtos")
    ws.append(["SKU", "Nome do produto", "Preço", "Estoque", "EAN", "Peso (kg)"])
    ws.append([12345, "Lâmpada H4", 39.9, 25, 7891234567895, 0.25])
    ws.append(["HZ-2002", "Palheta", "49,90", 3, None, 0.4])
    path = tmp_path / "base.xlsx"
    wb.save(path)
    analysis = ctx.imports.analyze(path)
    assert analysis.info.sheets == ["Capa", "Produtos"]
    analysis = ctx.imports.choose_table(analysis, path, sheet="Produtos")
    mapping = analysis.mapping()
    assert mapping["SKU"] == "sku" and mapping["EAN"] == "gtin"
    mapping["Peso (kg)"] = "weight_kg"
    batch = ctx.imports.plan(analysis, mapping)
    ctx.imports.commit(batch.id)
    lamp = ctx.products.get(ctx.products.id_for_sku("12345"))
    assert lamp.price_cents == 3990 and lamp.gtin == "7891234567895" and lamp.weight_g == 250
    assert ctx.products.get(ctx.products.id_for_sku("HZ-2002")).price_cents == 4990


def test_json_nested_records(ctx, tmp_path):
    payload = {"empresa": "Horizonte", "dados": {"itens": [
        {"sku": "J-1", "nome": "Retentor", "preco": "12,00", "estoque": 5,
         "fabricante": {"marca": "Sabó"}, "fotos": ["a.jpg", "b.jpg"]},
        {"sku": "J-2", "nome": "Junta", "preco": 8.5, "estoque": 2}]}}
    path = write(tmp_path / "base.json", json.dumps(payload, ensure_ascii=False))
    analysis = ctx.imports.analyze(path)
    assert {"fabricante.marca", "fotos"} <= set(analysis.headers)
    mapping = analysis.mapping()
    mapping["fabricante.marca"] = "brand"
    _, batch = analysis, ctx.imports.plan(analysis, mapping)
    ctx.imports.commit(batch.id)
    product = ctx.products.get(ctx.products.id_for_sku("J-1"))
    assert product.brand == "Sabó" and {m.reference for m in product.missing_media} == {"a.jpg", "b.jpg"}
    assert ctx.products.get(ctx.products.id_for_sku("J-2")).price_cents == 850


def test_mla_json_round_trip_keeps_variants_and_images(ctx, complete_product, tmp_path):
    product = complete_product("RT-1")
    from mla.core.models import ProductVariant
    product.variants = [ProductVariant("Cor: Azul", sku="RT-1-AZ", stock=2), ProductVariant("Cor: Preto",
                                                                                            sku="RT-1-PT", stock=3)]
    product.specs = {"Voltagem": "12 V"}
    ctx.catalog.save(product)
    export = tmp_path / "export" / "catalogo.json"
    export.parent.mkdir()
    ctx.import_export.export_json(export, [product.id])
    ctx.catalog.delete([product.id])
    analysis = ctx.imports.analyze(export)
    mapping = analysis.mapping()
    assert mapping["sku_pai"] == "parent_sku" and mapping["variacao"] == "variant_name"
    assert mapping["spec_Voltagem"] == "spec"
    batch = ctx.imports.plan(analysis, mapping)
    report = ctx.imports.commit(batch.id)
    assert report.counts["errors"] == 0
    restored = ctx.products.get(ctx.products.id_for_sku("RT-1"))
    assert [(v.name, v.sku, v.stock) for v in restored.variants] == [("Cor: Azul", "RT-1-AZ", 2),
                                                                     ("Cor: Preto", "RT-1-PT", 3)]
    assert len(restored.images) == 1 and restored.specs == {"Voltagem": "12 V"}


def test_xml_records_and_entities_refused(ctx, tmp_path):
    xml = ("<catalogo><info><gerado>2026</gerado></info><produtos>"
           "<produto codigo_sku='X-1'><nome>Correia</nome><preco>55,00</preco><imagens><imagem>c1.jpg</imagem>"
           "<imagem>c2.jpg</imagem></imagens></produto>"
           "<produto codigo_sku='X-2'><nome>Tensor</nome><preco>80,00</preco></produto></produtos></catalogo>")
    path = write(tmp_path / "base.xml", xml)
    analysis = ctx.imports.analyze(path)
    assert analysis.preview[0].values["imagens.imagem"] == "c1.jpg | c2.jpg"
    mapping = analysis.mapping()
    mapping["@codigo_sku"] = "sku"
    mapping["imagens.imagem"] = "images"
    batch = ctx.imports.plan(analysis, mapping)
    ctx.imports.commit(batch.id)
    assert ctx.products.get(ctx.products.id_for_sku("X-2")).price_cents == 8000
    bomb = write(tmp_path / "bomb.xml", '<!DOCTYPE x [<!ENTITY a "aaaa">]><x><p>&a;</p></x>')
    with pytest.raises(ImportProblem, match="DOCTYPE"):
        ctx.imports.analyze(bomb)


def test_single_record_xml(tmp_path):
    path = write(tmp_path / "um.xml", "<produto><sku>S-1</sku><nome>Único</nome><fotos><foto>a.jpg</foto>"
                                      "<foto>b.jpg</foto></fotos></produto>")
    rows = open_source(path).preview()
    assert len(rows) == 1 and rows[0].values["sku"] == "S-1" and rows[0].values["fotos.foto"] == "a.jpg | b.jpg"


def test_pdf_table_safe_and_ambiguous_rows(ctx, tmp_path, pdf_builder):
    pdf_table, _ = pdf_builder
    path = pdf_table(tmp_path / "catalogo.pdf", [
        ("Código", "Descrição", "Preço", "Estoque"),
        ("PDF-1", "Filtro de ar", "45,00", "7"),
        ("PDF-2", "Bomba de combustível", "389,90", ""),
    ])
    analysis = ctx.imports.analyze(path)
    assert analysis.headers == ["Código", "Descrição", "Preço", "Estoque"]
    assert analysis.preview[0].review == ""
    assert "células vazias" in analysis.preview[1].review
    batch = ctx.imports.plan(analysis, analysis.mapping())
    rows = {r.sku: r for r in ctx.imports.rows(batch.id)}
    assert rows["PDF-1"].action is ImportAction.CREATE
    assert rows["PDF-2"].action is ImportAction.REVIEW and rows["PDF-2"].decision == "skip"
    ctx.imports.commit(batch.id)
    assert ctx.products.id_for_sku("PDF-1") and ctx.products.id_for_sku("PDF-2") is None


def test_pdf_review_rows_need_explicit_inclusion(ctx, tmp_path, pdf_builder):
    pdf_table, _ = pdf_builder
    path = pdf_table(tmp_path / "c.pdf", [("Código", "Descrição", "Preço", "Estoque"), ("PDF-9", "Item", "9,00", "")])
    run_import(ctx, path, include_review=True)
    assert ctx.products.get(ctx.products.id_for_sku("PDF-9")).price_cents == 900


def test_pdf_technical_sheet(ctx, tmp_path, pdf_builder):
    _, make_pdf = pdf_builder
    path = make_pdf(tmp_path / "ficha.pdf", [(50, 800, "Ficha técnica"), (50, 770, "SKU: FT-1"),
                                             (50, 752, "Nome: Amortecedor dianteiro"), (50, 734, "Marca: Horizonte"),
                                             (50, 716, "Material: Aço")])
    analysis = ctx.imports.analyze(path)
    assert len(analysis.preview) == 1 and "Ficha técnica" in analysis.preview[0].review
    assert analysis.mapping()["SKU"] == "sku"


def test_scanned_pdf_is_refused(ctx, tmp_path, pdf_builder):
    _, make_pdf = pdf_builder
    with pytest.raises(ImportProblem, match="OCR"):
        ctx.imports.analyze(make_pdf(tmp_path / "scan.pdf", []))


# ------------------------------------------------------------------ ZIP and images
def test_zip_extraction_is_safe(tmp_path):
    archive = tmp_path / "pacote.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("catalogo/produtos.csv", "sku;nome\nZ-1;Item\n")
        zf.writestr("catalogo/fotos/Z-1.png", make_png(tmp_path / "z.png").read_bytes())
        zf.writestr("instalar.bat", "format c:")
        zf.writestr("planilha_macro.xlsm", "x")
        zf.writestr("../../fora.csv", "sku\n1\n")
        zf.writestr("__MACOSX/._lixo", "x")
    contents = extract_archive(archive, tmp_path / "staging")
    assert [p.name for p in contents.catalogs] == ["produtos.csv"]
    assert [p.name for p in contents.images] == ["Z-1.png"]
    reasons = dict(contents.skipped)
    assert "bloqueado" in reasons["instalar.bat"] and "bloqueado" in reasons["planilha_macro.xlsm"]
    assert "inseguro" in reasons["../../fora.csv"]
    assert not (tmp_path / "fora.csv").exists()


def test_zip_with_catalog_and_images(ctx, tmp_path):
    archive = tmp_path / "horizonte.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("produtos.csv", "sku;nome;preco;estoque;imagem\nZP-1;Coxim;70,00;3;fotos/coxim.png\n")
        zf.writestr("fotos/coxim.png", make_png(tmp_path / "c.png").read_bytes())
        zf.writestr("leia-me.exe", "MZ")
    analysis, batch, report = run_import(ctx, archive)
    assert analysis.format == "zip" and report.counts["created"] == 1
    assert len(ctx.products.get(ctx.products.id_for_sku("ZP-1")).images) == 1
    assert not analysis.staging_dir.exists(), "staging removed after commit"


def test_images_only_zip_matches_sku_and_resolves_pending(ctx, horizonte_csv, tmp_path):
    run_import(ctx, horizonte_csv)
    archive = tmp_path / "fotos.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("HZ-1003.png", make_png(tmp_path / "v.png", color=(1, 2, 3)).read_bytes())
        zf.writestr("sumida.jpg", (tmp_path / "v.png").read_bytes()[:0] + make_png(
            tmp_path / "s.png", color=(9, 9, 9)).read_bytes())
        zf.writestr("SEM-DONO.png", make_png(tmp_path / "x.png", color=(5, 5, 5)).read_bytes())
    analysis = ctx.imports.analyze(archive)
    assert analysis.images_only
    batch = ctx.imports.plan(analysis, {})
    rows = ctx.imports.rows(batch.id)
    assert {r.sku for r in rows if r.action is ImportAction.UPDATE} == {"HZ-1003", "HZ-1002"}
    assert any("Nenhum produto" in r.issues[0]["message"] for r in rows if r.action is ImportAction.SKIP)
    ctx.imports.commit(batch.id)
    pastilha = ctx.products.get(ctx.products.id_for_sku("HZ-1002"))
    assert len(pastilha.images) == 2 and pastilha.missing_media == []


def test_image_folder_association(ctx, horizonte_csv, tmp_path):
    run_import(ctx, horizonte_csv)
    folder = tmp_path / "fotos_novas"
    make_png(folder / "HZ-1003-1.png", color=(3, 3, 3))
    analysis = ctx.imports.analyze(folder)
    batch = ctx.imports.plan(analysis, {})
    ctx.imports.commit(batch.id)
    assert len(ctx.products.get(ctx.products.id_for_sku("HZ-1003")).images) == 1


# ------------------------------------------------------------------ variants
def test_variants_by_parent_sku_even_when_parent_comes_later(ctx, tmp_path):
    path = write(tmp_path / "v.csv", "sku;sku_pai;variacao;nome;preco;estoque\n"
                                     "CAM-P;CAM;Tamanho: P;;59,90;3\n"
                                     "CAM;;;Camiseta técnica;59,90;0\n"
                                     "CAM-M;CAM;Tamanho: M;;59,90;5\n"
                                     "ORF-1;NAO-EXISTE;Cor: Azul;;10;1\n")
    analysis, batch, report = run_import(ctx, path)
    rows = {r.sku: r for r in ctx.imports.rows(batch.id)}
    assert rows["ORF-1"].action is ImportAction.ERROR and "não está no arquivo" in rows["ORF-1"].issues[0]["message"]
    product = ctx.products.get(ctx.products.id_for_sku("CAM"))
    assert sorted((v.sku, v.stock) for v in product.variants) == [("CAM-M", 5), ("CAM-P", 3)]
    # second import updates a variation's stock through its own SKU
    again = write(tmp_path / "v2.csv", "sku;estoque\nCAM-M;9\n")
    run_import(ctx, again)
    assert {v.sku: v.stock for v in ctx.products.get(product.id).variants}["CAM-M"] == 9


# ------------------------------------------------------------------ compatibility import
def test_compatibility_import(ctx, horizonte_csv, tmp_path):
    run_import(ctx, horizonte_csv)
    path = write(tmp_path / "compat.csv", "sku;montadora;modelo;motor;anos;codigo_oem\n"
                                          "HZ-1002;Fiat;Uno;1.0;2010-2015;OEM-1\n"
                                          "HZ-1002;Fiat;Uno;1.0;2010-2015;OEM-1\n"
                                          "HZ-1002;VW;Gol;;2012 a 2016;\n"
                                          "NAO-EXISTE;Ford;Ka;;2014;\n"
                                          "HZ-1001;GM;Onix;;ano novo;\n")
    analysis = ctx.imports.analyze(path, target="compatibility")
    mapping = analysis.mapping()
    assert mapping == {"sku": "sku", "montadora": "brand", "modelo": "model", "motor": "version", "anos": "years",
                       "codigo_oem": "reference_code"}
    batch = ctx.imports.plan(analysis, mapping, ImportOptions(source=DataSource.CLIENT.value))
    actions = [r.action for r in ctx.imports.rows(batch.id)]
    assert actions == [ImportAction.CREATE, ImportAction.UNCHANGED, ImportAction.CREATE, ImportAction.ERROR,
                       ImportAction.ERROR]
    ctx.imports.commit(batch.id)
    items = ctx.compatibility.search("HZ-1002")
    assert [(c.brand, c.model, c.year_from, c.year_to) for c in items] == [("Fiat", "Uno", 2010, 2015),
                                                                          ("VW", "Gol", 2012, 2016)]
    assert all(c.verification is Verification.CONFIRMED for c in items)


def test_external_compatibility_starts_unverified(ctx, horizonte_csv, tmp_path):
    run_import(ctx, horizonte_csv)
    path = write(tmp_path / "ext.csv", "sku;marca;modelo\nHZ-1001;Fiat;Strada\n")
    run_import(ctx, path, target="compatibility", options=ImportOptions(source=DataSource.EXTERNAL.value))
    assert ctx.compatibility.search("Strada")[0].verification is Verification.UNVERIFIED


# ------------------------------------------------------------------ cancel, recovery, templates, scale
def test_cancel_during_commit_changes_nothing(ctx, tmp_path):
    lines = "".join(f"C-{n};Item {n};10,00;1\n" for n in range(120))
    path = write(tmp_path / "c.csv", "sku;nome;preco;estoque\n" + lines)
    analysis = ctx.imports.analyze(path)
    batch = ctx.imports.plan(analysis, analysis.mapping())
    cancel = threading.Event()

    def progress(done, total, message):
        if message.startswith("Gravando") and done >= 50:
            cancel.set()

    with pytest.raises(ImportCancelled):
        ctx.imports.commit(batch.id, progress, cancel)
    assert ctx.products.count() == 0
    stored = ctx.imports.get(batch.id)
    assert stored.status is ImportStatus.PLANNED and "nenhuma alteração" in stored.message
    ctx.imports.commit(batch.id)  # can be confirmed again later
    assert ctx.products.count() == 120


def test_cancel_during_analysis(ctx, tmp_path):
    path = write(tmp_path / "c.csv", "sku;nome\n" + "".join(f"K-{n};x\n" for n in range(1200)))
    analysis = ctx.imports.analyze(path)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ImportCancelled):
        ctx.imports.plan(analysis, analysis.mapping(), cancel=cancel)
    assert ctx.imports.history()[0].status is ImportStatus.CANCELLED


def test_row_error_does_not_stop_others(ctx, tmp_path):
    path = write(tmp_path / "e.csv", "sku;nome\nE-1;Um\nE-2;Dois\n")
    analysis = ctx.imports.analyze(path)
    batch = ctx.imports.plan(analysis, analysis.mapping())
    ctx.catalog.save(Product(internal_name="Criado antes", sku="E-1"))  # appears after the analysis
    report = ctx.imports.commit(batch.id)
    assert report.counts["created"] == 1 and report.counts["errors"] == 1
    assert "passou a existir" in ctx.imports.rows(batch.id)[0].outcome


def test_recovery_after_restart(ctx, paths, tmp_path):
    path = write(tmp_path / "r.csv", "sku;nome\nR-1;Um\n")
    analysis = ctx.imports.analyze(path)
    batch = ctx.imports.plan(analysis, analysis.mapping())
    ctx.imports.repo.update_batch(batch.id, status=ImportStatus.COMMITTING)  # app closed mid-commit
    from mla.services.context import AppContext
    reopened = AppContext.open(paths)
    try:
        assert reopened.recovered_imports == 1
        stored = reopened.imports.get(batch.id)
        assert stored.status is ImportStatus.PLANNED and "desfeita" in stored.message
        reopened.imports.commit(batch.id)
        assert reopened.products.id_for_sku("R-1")
    finally:
        reopened.close()


def test_templates_are_saved_and_applied(ctx, tmp_path):
    first = write(tmp_path / "a.csv", "cod;nome_item;vlr\nT-1;Coisa;10\n")
    analysis = ctx.imports.analyze(first)
    mapping = {"cod": "sku", "nome_item": "internal_name", "vlr": "price_cents"}
    ctx.imports.save_template("ERP Horizonte", analysis, mapping)
    second = write(tmp_path / "b.csv", "cod;nome_item;vlr\nT-2;Outra;20\n")
    again = ctx.imports.analyze(second)
    assert again.template.name == "ERP Horizonte" and again.mapping() == mapping
    assert all(s.confidence == "template" for s in again.suggestions)


def test_discard_before_confirmation(ctx, horizonte_csv):
    analysis = ctx.imports.analyze(horizonte_csv)
    batch = ctx.imports.plan(analysis, analysis.mapping())
    ctx.imports.discard(batch.id)
    assert ctx.products.count() == 0
    assert ctx.imports.get(batch.id).status is ImportStatus.DISCARDED
    with pytest.raises(ImportProblem):
        ctx.imports.commit(batch.id)


def test_large_base_in_chunks(ctx, tmp_path):
    lines = "".join(f"L-{n:05d};Produto {n};{n % 90 + 10},90;{n % 7}\n" for n in range(2600))
    path = write(tmp_path / "grande.csv", "sku;nome;preco;estoque\n" + lines)
    analysis = ctx.imports.analyze(path)
    seen = []
    batch = ctx.imports.plan(analysis, analysis.mapping(), progress=lambda d, t, m: seen.append(d))
    assert seen[:5] == [500, 1000, 1500, 2000, 2500]
    assert ctx.imports.count_rows(batch.id) == 2600
    assert len(ctx.imports.rows(batch.id, limit=100, offset=2550)) == 50
    ctx.imports.commit(batch.id)
    assert ctx.products.count() == 2600
    assert len(ctx.catalog.search(ProductQuery(limit=100))) == 100


def test_legacy_csv_update_keeps_images_and_exports_master_fields(ctx, complete_product, tmp_path):
    product = complete_product("LG-1", gtin="7891234567895", cost_cents=5000, supplier="Distribuidora X")
    ctx.catalog.save(product)
    out = tmp_path / "exp" / "catalogo.csv"
    out.parent.mkdir()
    ctx.import_export.export_csv(out, [product.id])
    header = out.read_text(encoding="utf-8-sig").splitlines()[0]
    assert "gtin" in header and "cost" in header and "supplier" in header
    update = write(tmp_path / "upd.csv", "sku;internal_name;price\nLG-1;Suporte LG-1;150,00\n")
    result = ctx.import_export.import_csv(update, "update")
    assert result.updated == 1
    after = ctx.products.get(product.id)
    assert after.price_cents == 15000 and len(after.images) == 1, "update by file must not drop images"
