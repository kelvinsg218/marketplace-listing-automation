"""Template Inspector: read-only analysis of an official bulk-listing workbook (XLSX).

It reports facts with cell coordinates and never invents a layout. Rules come from the official help pages
(docs/MLA_MERCADOLIVRE_RESEARCH.md) and from the structure of a real template analysed on 2026-11-01
(docs/MLA_OFFICIAL_TEMPLATE_ANALYSIS.md): header row with "Obrigatório" right below it, helper columns
BUYBOX_FORMULA / HIDDEN_PICTURES, data validations pointing at the very hidden "extra info" sheet, conditional
formatting that encodes title length and minimum price, and a send-by deadline on the "Ajuda" sheet.
Hidden sheets are never previewed: in real files they hold the account binding (identifiers).
"""
from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter, range_boundaries

INSPECTOR_VERSION = 2
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_ZIP_ENTRIES = 5000
SCAN_ROWS = 30          # titles, headers and instructions are at the top of each sheet
PREVIEW_ROWS = 15
PREVIEW_COLS = 60
CELL_TEXT_MAX = 160
MAX_LIST_OPTIONS = 300

MONTHS = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
          "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
# "Faça isso até 10 de setembro" (help capture, P2 p.2) and "Faça isso antes de 1 de dezembro" (real file).
_DEADLINE = re.compile(r"(?:ate|antes de)\s+(?:o\s+dia\s+)?(\d{1,2})\s+de\s+([a-z]+)(?:\s+de\s+(\d{4}))?")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Placeholders the official file pre-fills in data rows; they mean "no value" (conditional formatting paints a
# required cell red when it still holds one of them).
PLACEHOLDERS = ("Insira ou selecione um valor", "Selecionar")
HELPER_HEADERS = ("BUYBOX_FORMULA", "HIDDEN_PICTURES")

MARKERS = {
    "required": ("obrigatorio",),
    "error_summary": ("resumo de erros",),
    "catalog_code": ("codigo de catalogo ml", "codigo do catalogo ml"),
    "photos": ("fotos",),
    "catalog_optional_note": ("para catalogo, nao e necessario preencher este dado",),
}


class TemplateRejected(ValueError):
    """The file is not a workbook we can safely inspect."""


def norm(text: object) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()
    return re.sub(r"\s+", " ", plain).strip()


def check_package(data: bytes) -> list[str]:
    """Structural safety checks before openpyxl touches the file. Returns warnings; raises when unsafe."""
    if len(data) > MAX_FILE_BYTES:
        raise TemplateRejected(f"Arquivo maior que {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    if not data.startswith(b"PK\x03\x04"):
        raise TemplateRejected("O arquivo não é um XLSX (Excel 2007 ou mais recente).")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise TemplateRejected("Arquivo XLSX corrompido.") from exc
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
        raise TemplateRejected("Conteúdo descompactado grande demais; arquivo recusado por segurança.")
    names = {i.filename for i in infos}
    if "xl/workbook.xml" not in names:
        raise TemplateRejected("O pacote não contém uma pasta de trabalho do Excel.")
    warnings = []
    if any(n.lower().endswith("vbaproject.bin") for n in names):
        warnings.append("O arquivo contém macros; elas não são carregadas nem executadas pelo MLA.")
    if any(n.startswith("xl/externalLinks/") for n in names):
        warnings.append("O arquivo tem vínculos externos; eles não são seguidos.")
    return warnings


@dataclass
class _Hit:
    key: str
    cell: str
    text: str


def _cell_text(value: object) -> str:
    text = str(value)
    return text if len(text) <= CELL_TEXT_MAX else text[:CELL_TEXT_MAX] + "…"


def find_deadline(text: str, reference: date, technical_dates: list[date] | None = None) -> dict | None:
    """'Faça isso antes de 1 de dezembro' -> date. Without a year in the text, a machine-readable date stored in
    the file with the same day/month fixes the year; otherwise the year is inferred and flagged."""
    m = _DEADLINE.search(norm(text))
    if not m or m.group(2) not in MONTHS:
        return None
    day, month = int(m.group(1)), MONTHS[m.group(2)]
    year = int(m.group(3)) if m.group(3) else None
    source = "texto" if year else None
    if year is None:
        match = next((d for d in technical_dates or [] if (d.day, d.month) == (day, month)), None)
        if match:
            year, source = match.year, "texto + data técnica do arquivo"
    inferred = year is None
    if inferred:
        # Nearest occurrence not earlier than ~6 months before the upload.
        year = reference.year
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if (candidate - reference).days > 183:
            year -= 1
        elif (reference - candidate).days > 183:
            year += 1
        source = "texto (ano deduzido)"
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None
    return {"text": text.strip()[:200], "date": parsed.isoformat(), "year_inferred": inferred, "source": source}


def _technical_dates(wb) -> list[date]:
    out = []
    for ws in wb.worksheets:
        if ws.sheet_state == "visible":
            continue
        for row in ws.iter_rows(min_row=1, max_row=3):
            for c in row:
                v = c.value
                if isinstance(v, str) and _ISO_DATE.match(v.strip()):
                    try:
                        out.append(date.fromisoformat(v.strip()))
                    except ValueError:
                        pass
                elif hasattr(v, "year") and hasattr(v, "month"):
                    out.append(date(v.year, v.month, v.day))
    return out


def _list_options(wb, formula: str) -> list[str] | None:
    """Resolves "'extra info'!$A$2:$B$2" (or an inline "a,b" list) to its values."""
    formula = (formula or "").strip()
    if formula.startswith('"') and formula.endswith('"'):
        return [x.strip() for x in formula[1:-1].split(",")][:MAX_LIST_OPTIONS]
    m = re.match(r"^'?([^'!]+)'?!\$?([A-Z]+)\$?(\d+):\$?([A-Z]+)\$?(\d+)$", formula)
    if not m or m.group(1) not in wb.sheetnames:
        return None
    ws = wb[m.group(1)]
    min_col, min_row, max_col, max_row = range_boundaries(f"{m.group(2)}{m.group(3)}:{m.group(4)}{m.group(5)}")
    values = []
    for row in ws.iter_rows(min_row=min_row, max_row=max_row, min_col=min_col, max_col=max_col):
        values += [str(c.value) for c in row if c.value not in (None, "")]
    return values[:MAX_LIST_OPTIONS]


def _num(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _layout(wb, ws, header_row: int | None, hidden_cols: set[str]) -> dict | None:
    """Column specifications of a category sheet. Only what the file states is recorded."""
    if header_row is None:
        return None
    headers = {c.column_letter: str(c.value).strip() for c in ws[header_row] if c.value not in (None, "")}
    required = {c.column_letter for c in ws[header_row + 1] if norm(c.value) == "obrigatorio"}
    help_text = {c.column_letter: _cell_text(c.value) for c in ws[header_row + 2] if c.value not in (None, "")}
    helper = {col: h for col, h in headers.items() if h in HELPER_HEADERS}
    data_start = None
    capacity = 0
    if helper:
        col = next(iter(helper))
        for row in ws.iter_rows(min_row=header_row + 1, min_col=column_index_from_string(col),
                                max_col=column_index_from_string(col)):
            cell = row[0]
            if isinstance(cell.value, str) and cell.value.startswith("="):
                data_start = data_start or cell.row
                capacity += 1
    specs: dict[str, dict] = {col: {"col": col, "header": h, "required": col in required, "help": help_text.get(col, ""),
                                    "hidden": col in hidden_cols, "helper": col in helper, "formula": False,
                                    "kind": None, "options": None, "strict": False, "max_length": None,
                                    "min_value": None, "default": None}
                              for col, h in headers.items()}
    for dv in ws.data_validations.dataValidation:
        for rng in str(dv.sqref).split():
            min_col, min_row, max_col, _ = range_boundaries(rng)
            if data_start is None or min_row < data_start - 1:
                continue
            for ci in range(min_col, max_col + 1):
                spec = specs.get(get_column_letter(ci))
                if spec is None:
                    continue
                spec["kind"] = dv.type
                spec["strict"] = bool(dv.showErrorMessage)
                if dv.type == "list":
                    spec["options"] = _list_options(wb, dv.formula1)
                elif dv.type == "textLength" and dv.operator in (None, "lessThanOrEqual", "between"):
                    spec["max_length"] = int(_num(dv.formula2 if dv.operator == "between" else dv.formula1) or 0) or None
    # Conditional formatting encodes limits the validations do not: title length and minimum price.
    for rng in ws.conditional_formatting:
        col = get_column_letter(range_boundaries(str(rng.sqref).split()[0])[0])
        spec = specs.get(col)
        for rule in rng.rules:
            for f in rule.formula or []:
                if spec is None:
                    continue
                m = re.search(r"LEN\(INDIRECT\(ADDRESS\(ROW\(\),COLUMN\(\)\)\)\)\s*>\s*(\d+)", f)
                if m:
                    spec["max_length"] = int(m.group(1))
                m = re.search(rf"\${col}\d+\s*<\s*([\d.]+)", f)
                if m:
                    spec["min_value"] = float(m.group(1))
    if data_start:
        for c in ws[data_start]:
            spec = specs.get(c.column_letter)
            if spec is None or c.value in (None, ""):
                continue
            if isinstance(c.value, str) and c.value.startswith("="):
                spec["formula"] = True
            else:
                spec["default"] = _cell_text(c.value)
    for spec in specs.values():
        # Input columns: everything except helpers and computed formulas. "Fotos" holds a formula in catalog sheets
        # ("Este produto tem imagens do catálogo…") that the seller replaces with URLs, so it stays writable.
        spec["writable"] = not spec["helper"] and (not spec["formula"] or norm(spec["header"]) == "fotos")
    fee = None
    for spec in specs.values():
        if norm(spec["header"]).startswith("tarifa de venda") and data_start:
            f = str(ws[f"{spec['col']}{data_start}"].value or "")
            rates = re.findall(r'="(\w[^"]*)",\s*IF\(\(ROUND\(\(SUMIF\(.*?\)\)\*([\d.]+)/100', f)
            fee = {name: float(rate) for name, rate in rates} or None
    return {
        "header_row": header_row,
        "data_start_row": data_start,
        "capacity": capacity,
        "catalog_sheet": any(norm(h) in MARKERS["catalog_code"] for h in headers.values()),
        "variation_columns": [c for c, h in headers.items() if norm(h).startswith("varia por:")],
        "fee_percent": fee,
        "columns": list(specs.values()),
    }


def inspect_workbook(data: bytes, *, today: date) -> dict:
    """Returns a JSON-serializable report. Raises TemplateRejected for files that cannot be inspected safely."""
    warnings = check_package(data)
    try:
        wb = load_workbook(io.BytesIO(data), read_only=False, data_only=False, keep_vba=False, keep_links=False)
    except Exception as exc:  # openpyxl raises many types for malformed packages
        raise TemplateRejected(f"Não foi possível ler a planilha: {type(exc).__name__}.") from exc

    sheets, deadline = [], None
    tech_dates = _technical_dates(wb)
    help_sheet = next((ws.title for ws in wb.worksheets if norm(ws.title) == "ajuda"), None)
    if help_sheet is None:
        warnings.append('Nenhuma aba "Ajuda" encontrada; a documentação oficial descreve uma (P2 p.1).')

    for index, ws in enumerate(wb.worksheets):
        visible = ws.sheet_state == "visible"
        hits: list[_Hit] = []
        row_fill: dict[int, int] = {}
        row_markers: dict[int, int] = {}
        formulas = 0
        for row in ws.iter_rows(min_row=1, max_row=max(ws.max_row, 1)):
            for cell in row:
                value = cell.value
                if value is None or value == "":
                    continue
                if isinstance(value, str) and value.startswith("="):
                    formulas += 1
                if cell.row > SCAN_ROWS or not visible:
                    continue
                row_fill[cell.row] = row_fill.get(cell.row, 0) + 1
                text = norm(value)
                for key, needles in MARKERS.items():
                    if any(n in text for n in needles):
                        hits.append(_Hit(key, cell.coordinate, _cell_text(value)))
                        row_markers[cell.row] = row_markers.get(cell.row, 0) + 1
                if ws.title == help_sheet and deadline is None and isinstance(value, str):
                    found = find_deadline(value, today, tech_dates)
                    if found:
                        deadline = {**found, "sheet": ws.title, "cell": cell.coordinate}
        preview = []
        if visible:
            for r in range(1, min(ws.max_row, PREVIEW_ROWS) + 1):
                preview.append([_cell_text(ws.cell(r, c).value) if ws.cell(r, c).value is not None else ""
                                for c in range(1, min(ws.max_column, PREVIEW_COLS) + 1)])
        validations = [{"sqref": str(dv.sqref), "type": dv.type or "", "formula1": _cell_text(dv.formula1 or ""),
                        "allow_blank": bool(dv.allow_blank), "strict": bool(dv.showErrorMessage)}
                       for dv in ws.data_validations.dataValidation]
        cf_rules = sum(len(r.rules) for r in ws.conditional_formatting)
        # Header row: the row right above most "Obrigatório" markers (official layout); otherwise candidates.
        req_rows = [h for h in hits if h.key == "required"]
        header_row = None
        if req_rows:
            counts: dict[int, int] = {}
            for h in req_rows:
                r = int(re.sub(r"[A-Z]+", "", h.cell))
                counts[r] = counts.get(r, 0) + 1
            top = max(counts, key=counts.get)
            if counts[top] >= 2 and top > 1:
                header_row = top - 1
        candidates = sorted(row_fill, key=lambda r: (-(row_fill[r] + 3 * row_markers.get(r, 0)), r))[:3]
        if header_row and header_row not in candidates:
            candidates = [header_row] + candidates[:2]
        hidden_cols = {k for k, d in ws.column_dimensions.items() if d.hidden}
        layout = _layout(wb, ws, header_row, hidden_cols) if visible and ws.title != help_sheet else None
        sheets.append({
            "index": index,
            "name": ws.title,
            "state": ws.sheet_state,  # visible | hidden | veryHidden
            "is_help": ws.title == help_sheet,
            "max_row": ws.max_row,
            "max_column": ws.max_column,
            "max_column_letter": get_column_letter(max(ws.max_column, 1)),
            "merged_ranges": len(ws.merged_cells.ranges),
            "formula_cells": formulas,
            "conditional_formatting_rules": cf_rules,
            "protected": bool(ws.protection.sheet),
            "hidden_columns": sorted(hidden_cols),
            "data_validations": validations[:200] if visible else [],
            "data_validation_count": len(validations),
            "markers": [vars(h) for h in hits][:500],
            "header_candidates": [{"row": r, "filled_cells": row_fill[r], "marker_hits": row_markers.get(r, 0)}
                                  for r in sorted(candidates)],
            "layout": layout,
            "preview": preview,
        })

    if help_sheet and deadline is None:
        warnings.append("Não encontramos a data limite de envio na aba Ajuda; informe-a manualmente.")
    if not any(s["layout"] and s["layout"]["data_start_row"] for s in sheets):
        warnings.append("Nenhuma aba de categoria com a estrutura oficial conhecida (cabeçalho + linhas de dados).")
    return {
        "inspector_version": INSPECTOR_VERSION,
        "sheet_count": len(sheets),
        "sheets": sheets,
        "sheet_order": [s["name"] for s in sheets],
        "help_sheet": help_sheet,
        "hidden_sheets": [s["name"] for s in sheets if s["state"] != "visible"],
        "defined_names": sorted(list(wb.defined_names.keys()))[:200],
        "workbook_protected": bool(wb.security and wb.security.lockStructure),
        "deadline": deadline,
        "warnings": warnings,
    }


def sheet_columns(report: dict, sheet_name: str, header_row: int) -> list[dict]:
    """Columns of the confirmed header row. Uses the inspected layout when it matches, else the preview."""
    sheet = next((s for s in report.get("sheets", []) if s["name"] == sheet_name), None)
    if sheet is None:
        raise KeyError(sheet_name)
    layout = sheet.get("layout")
    if layout and layout["header_row"] == header_row:
        return [{"col": c["col"], "header": c["header"], "required": c["required"]}
                for c in layout["columns"] if c["writable"]]
    if not 1 <= header_row <= len(sheet["preview"]):
        raise IndexError(header_row)
    required_cells = {h["cell"] for h in sheet["markers"] if h["key"] == "required"}
    columns = []
    for c, text in enumerate(sheet["preview"][header_row - 1], start=1):
        if not text:
            continue
        letter = get_column_letter(c)
        # "Obrigatório" sits in the header cell or right below it (P2 p.4, P3 p.4, real template row 4).
        required = any(cell in required_cells for cell in (f"{letter}{header_row}", f"{letter}{header_row + 1}"))
        columns.append({"col": letter, "header": text, "required": required})
    return columns


def column_specs(report: dict, sheet_name: str) -> dict[str, dict]:
    sheet = next((s for s in report.get("sheets", []) if s["name"] == sheet_name), None)
    layout = (sheet or {}).get("layout") or {}
    return {c["col"]: c for c in layout.get("columns", [])}


def compare_reports(old: dict, new: dict) -> dict:
    """Template change detection: what changed between two inspected versions (no guessing about why)."""
    def sheets(r):
        return {s["name"]: s for s in r.get("sheets", [])}
    o, n = sheets(old), sheets(new)
    diff = {"sheets_added": sorted(set(n) - set(o)), "sheets_removed": sorted(set(o) - set(n)),
            "sheet_order_changed": [s for s in old.get("sheet_order", []) if s in n] !=
                                   [s for s in new.get("sheet_order", []) if s in o],
            "sheets": {}}
    for name in sorted(set(o) & set(n)):
        lo, ln = o[name].get("layout") or {}, n[name].get("layout") or {}
        co = {c["header"]: c for c in lo.get("columns", [])}
        cn = {c["header"]: c for c in ln.get("columns", [])}
        changes = {
            "columns_added": sorted(set(cn) - set(co)),
            "columns_removed": sorted(set(co) - set(cn)),
            "columns_moved": sorted(h for h in set(co) & set(cn) if co[h]["col"] != cn[h]["col"]),
            "became_required": sorted(h for h in set(co) & set(cn) if cn[h]["required"] and not co[h]["required"]),
            "no_longer_required": sorted(h for h in set(co) & set(cn) if co[h]["required"] and not cn[h]["required"]),
            "options_changed": sorted(h for h in set(co) & set(cn) if co[h].get("options") != cn[h].get("options")),
            "header_row_changed": lo.get("header_row") != ln.get("header_row"),
            "data_start_changed": lo.get("data_start_row") != ln.get("data_start_row"),
            "formula_cells_delta": n[name]["formula_cells"] - o[name]["formula_cells"],
            "validations_delta": n[name].get("data_validation_count", 0) - o[name].get("data_validation_count", 0),
        }
        if any(v for v in changes.values()):
            diff["sheets"][name] = changes
    diff["breaking"] = bool(diff["sheets_removed"] or any(
        c["columns_removed"] or c["columns_moved"] or c["became_required"] or c["header_row_changed"]
        or c["data_start_changed"] for c in diff["sheets"].values()))
    return diff
