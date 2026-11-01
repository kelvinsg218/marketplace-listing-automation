"""Workbook Writer: fills a COPY of the seller's official bulk-listing workbook.

Design (docs/MLA_OFFICIAL_TEMPLATE_ANALYSIS.md §6):
- Only the target sheet's XML part changes, plus `<calcPr fullCalcOnLoad="1"/>` in workbook.xml. Every other ZIP
  part (other sheets, the very hidden "extra info" sheet, shared strings, styles, images, relationships) is copied
  byte for byte. openpyxl is never used to save: it drops drawings/images and rewrites the whole package.
- Only writable data cells of the target rows change (rows from `data_start_row`, columns marked writable by the
  inspector). Header, "Obrigatório", help and link rows, helper columns (BUYBOX_FORMULA, HIDDEN_PICTURES) and
  computed formula columns are never touched.
- Text goes in as inline strings (shared strings stay untouched); numbers as numbers; each cell keeps its style.
- In written rows the cached results of formula cells are removed (they would be stale: title length 0, fee "-")
  and Excel is told to recalculate on open. Whether Mercado Livre's processor recalculates is NOT known: it is the
  main compatibility risk until a controlled acceptance test is done.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from xml.sax.saxutils import escape

from openpyxl.utils import column_index_from_string


class WriterError(ValueError):
    pass


@dataclass(frozen=True)
class WriteResult:
    data: bytes
    sheet_part: str
    rows_written: int
    cells_written: int


_CELL_RE = r'<c r="{ref}"(?P<attrs>[^>]*?)(?:/>|>(?P<body>.*?)</c>)'


def _sheet_part(z: zipfile.ZipFile, sheet_name: str) -> str:
    wb = z.read("xl/workbook.xml").decode("utf-8")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    for m in re.finditer(r"<sheet\b[^>]*/>", wb):
        tag = m.group(0)
        name = re.search(r'name="([^"]*)"', tag)
        rid = re.search(r'r:id="([^"]+)"', tag)
        if name and rid and name.group(1) == escape(sheet_name, {'"': "&quot;"}):
            target = re.search(rf'Id="{rid.group(1)}"[^>]*Target="([^"]+)"', rels) or \
                re.search(rf'Target="([^"]+)"[^>]*Id="{rid.group(1)}"', rels)
            if not target:
                break
            path = target.group(1).lstrip("/")
            return path if path.startswith("xl/") else f"xl/{path}"
    raise WriterError(f"Aba não encontrada no arquivo: {sheet_name}")


def _cell_xml(ref: str, style: str, value: object, numeric: bool) -> str:
    s = f' s="{style}"' if style else ""
    if value is None or value == "":
        return f'<c r="{ref}"{s}/>'
    if numeric:
        return f'<c r="{ref}"{s} t="n"><v>{value}</v></c>'
    text = escape(str(value))
    return f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _col_of(ref: str) -> int:
    return column_index_from_string(re.match(r"[A-Z]+", ref).group(0))


def _patch_row(row_xml: str, rnum: int, cells: dict[str, tuple[object, bool]]) -> tuple[str, int]:
    open_tag = re.match(r"<row\b[^>]*?/?>", row_xml).group(0)
    if open_tag.endswith("/>"):
        open_tag, inner = open_tag[:-2] + ">", ""
    else:
        inner = row_xml[len(open_tag):-len("</row>")]
    # Formula cells of a written row: drop the stale cached result so nothing outdated is read.
    inner = re.sub(r"(<c\b[^>]*>(?:(?!</c>).)*?</f>)\s*(?:<v>[^<]*</v>|<v/>)", r"\1", inner, flags=re.S)
    written = 0
    for col, (value, numeric) in cells.items():
        ref = f"{col}{rnum}"
        m = re.search(_CELL_RE.format(ref=ref), inner, flags=re.S)
        if m:
            style = re.search(r'\bs="(\d+)"', m.group("attrs") or "")
            inner = inner[:m.start()] + _cell_xml(ref, style.group(1) if style else "", value, numeric) + inner[m.end():]
        else:
            new = _cell_xml(ref, "", value, numeric)
            target = _col_of(ref)
            pos = len(inner)
            for c in re.finditer(r'<c r="([A-Z]+)\d+"', inner):
                if column_index_from_string(c.group(1)) > target:
                    pos = c.start()
                    break
            inner = inner[:pos] + new + inner[pos:]
        written += 1
    return f"{open_tag}{inner}</row>", written


def fill(template: bytes, sheet_name: str, layout: dict, rows: list[dict[str, object]]) -> WriteResult:
    """rows: one dict per data row, {column letter: value}. Only writable columns are accepted."""
    if not layout or not layout.get("data_start_row"):
        raise WriterError("A aba não tem a estrutura oficial reconhecida (linhas de dados).")
    capacity = layout.get("capacity") or 0
    if len(rows) > capacity:
        raise WriterError(f"A aba comporta {capacity} linhas; o lote tem {len(rows)}. Divida o lote.")
    specs = {c["col"]: c for c in layout["columns"]}
    for row in rows:
        for col in row:
            spec = specs.get(col)
            if spec is None or not spec.get("writable"):
                raise WriterError(f"Coluna {col} não é um campo de preenchimento; não pode ser alterada.")
    src = zipfile.ZipFile(io.BytesIO(template))
    part = _sheet_part(src, sheet_name)
    sheet = src.read(part).decode("utf-8")
    start = layout["data_start_row"]
    cells_total = 0
    for i, row in enumerate(rows):
        rnum = start + i
        m = re.search(rf'<row r="{rnum}"(?:[^>]*/>|[^>]*>.*?</row>)', sheet, flags=re.S)
        if not m:
            raise WriterError(f"Linha {rnum} não existe no modelo oficial.")
        cells = {col: (value, specs[col].get("kind") == "decimal" and _is_number(value))
                 for col, value in row.items()}
        new_row, n = _patch_row(m.group(0), rnum, cells)
        sheet = sheet[:m.start()] + new_row + sheet[m.end():]
        cells_total += n
    workbook = src.read("xl/workbook.xml").decode("utf-8")
    if "<calcPr/>" in workbook:
        workbook = workbook.replace("<calcPr/>", '<calcPr fullCalcOnLoad="1"/>', 1)
    elif "<calcPr " in workbook and "fullCalcOnLoad" not in workbook:
        workbook = workbook.replace("<calcPr ", '<calcPr fullCalcOnLoad="1" ', 1)
    elif "<calcPr" not in workbook:
        workbook = workbook.replace("</sheets>", '</sheets><calcPr fullCalcOnLoad="1"/>', 1)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            if info.filename == part:
                data = sheet.encode("utf-8")
            elif info.filename == "xl/workbook.xml":
                data = workbook.encode("utf-8")
            else:
                data = src.read(info)
            dst.writestr(info, data, compress_type=info.compress_type)
    return WriteResult(out.getvalue(), part, len(rows), cells_total)


def _is_number(value: object) -> bool:
    if isinstance(value, (int, float)):
        return True
    try:
        float(str(value))
        return str(value).strip() != ""
    except ValueError:
        return False


def verify(original: bytes, output: bytes, sheet_part: str) -> list[str]:
    """Integrity checks after writing. Returns problems (empty = ok)."""
    problems = []
    a, b = zipfile.ZipFile(io.BytesIO(original)), zipfile.ZipFile(io.BytesIO(output))
    if a.namelist() != b.namelist():
        problems.append("A lista ou a ordem das partes do arquivo mudou.")
    for name in a.namelist():
        if name in (sheet_part, "xl/workbook.xml") or name not in b.namelist():
            continue
        if a.read(name) != b.read(name):
            problems.append(f"Parte alterada indevidamente: {name}")
    sa, sb = a.read(sheet_part).decode("utf-8"), b.read(sheet_part).decode("utf-8")
    for tag in ("dataValidation ", "conditionalFormatting", "mergeCell ", "hyperlink ", "col "):
        if sa.count(f"<{tag}") != sb.count(f"<{tag}"):
            problems.append(f"Estrutura da aba alterada: {tag.strip()}")
    if re.sub(r"<sheetData>.*</sheetData>", "", sa, flags=re.S) != re.sub(r"<sheetData>.*</sheetData>", "", sb, flags=re.S):
        problems.append("Algo fora das células foi alterado na aba.")
    wa = re.sub(r"<calcPr[^>]*/>", "", a.read("xl/workbook.xml").decode("utf-8"))
    wb = re.sub(r"<calcPr[^>]*/>", "", b.read("xl/workbook.xml").decode("utf-8"))
    if wa != wb:
        problems.append("workbook.xml mudou além do pedido de recálculo.")
    try:
        from openpyxl import load_workbook
        load_workbook(io.BytesIO(output), read_only=True).close()
    except Exception as exc:  # pragma: no cover - reported, not raised
        problems.append(f"O arquivo gerado não abre no leitor de teste: {type(exc).__name__}")
    return problems
