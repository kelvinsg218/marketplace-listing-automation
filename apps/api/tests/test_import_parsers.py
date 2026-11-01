"""Import parsers (migrated from the discontinued desktop test-suite, tests/unit/test_imports.py).

Only the tests of pure logic were kept; the desktop import service tests (SQLite plan/commit) were retired with it.
"""
import zipfile  # noqa: F401

import pytest  # noqa: F401
from helpers import make_png  # noqa: F401

from mla_api.importing.archive import extract_archive  # noqa: F401
from mla_api.importing.mapping import normalize_key, suggest_mapping  # noqa: F401
from mla_api.importing.readers import SourceError, detect_format, open_source  # noqa: F401

CSV_HEADER = "codigo;descricao;preco_venda;saldo;marca;ean;foto\n"


def write(path, text, encoding="utf-8"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding)
    return path


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


def test_single_record_xml(tmp_path):
    path = write(tmp_path / "um.xml", "<produto><sku>S-1</sku><nome>Único</nome><fotos><foto>a.jpg</foto>"
                                      "<foto>b.jpg</foto></fotos></produto>")
    rows = open_source(path).preview()
    assert len(rows) == 1 and rows[0].values["sku"] == "S-1" and rows[0].values["fotos.foto"] == "a.jpg | b.jpg"


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


def test_alternative_erp_column_names_are_recognised():
    from mla_api.importing.mapping import suggest_mapping
    headers = ["Cód. Produto", "Descrição do item", "Título para anúncio", "Comp (cm)", "Larg (cm)", "Alt (cm)",
               "Qtd Estoque"]
    found = {s.column: (s.field, s.confidence) for s in suggest_mapping(headers, [])}
    assert found["Descrição do item"] == ("internal_name", "probable")  # the user confirms it
    assert found["Título para anúncio"][0] == "title"
    assert [found[h][0] for h in ("Comp (cm)", "Larg (cm)", "Alt (cm)")] == ["length_cm", "width_cm", "height_cm"]
    compat = {s.column: s.field for s in suggest_mapping(["Marca do veículo", "Modelo do veículo"], [],
                                                          "compatibility")}
    assert compat == {"Marca do veículo": "brand", "Modelo do veículo": "model"}


# --- image headers (replaces the Qt-based desktop test) ---------------------------------------------------------
def test_image_headers_without_pillow(tmp_path):
    from mla_api.domain.image_info import ImageError, read_image_info, read_image_info_bytes
    png = make_png(tmp_path / "a.png", 640, 480)
    assert (read_image_info(png).format, read_image_info(png).width, read_image_info(png).height) == ("png", 640, 480)
    # Minimal JPEG: SOI + SOF0 segment with 1200x900.
    jpeg = b"\xff\xd8" + b"\xff\xc0" + bytes([0, 17, 8]) + (900).to_bytes(2, "big") + (1200).to_bytes(2, "big") + b"\x03" + b"\x00" * 9
    info = read_image_info_bytes(jpeg)
    assert (info.format, info.width, info.height) == ("jpeg", 1200, 900)
    webp = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"VP8X" + b"\x00" * 8 + (1199).to_bytes(3, "little") + (799).to_bytes(3, "little")
    assert read_image_info_bytes(webp).width == 1200
    with pytest.raises(ImageError):
        read_image_info_bytes(b"not an image at all")


def test_compatibility_years():
    from mla_api.importing.compatibility import CompatibilityError, parse_years
    assert parse_years("2010-2015") == (2010, 2015)
    assert parse_years("até 2014") == (None, 2014)
    assert parse_years("2018+") == (2018, None)
    with pytest.raises(CompatibilityError):
        parse_years("abc")
