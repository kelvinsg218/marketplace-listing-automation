"""Template Inspector: read-only analysis of an official bulk-listing workbook (XLSX).

It reports facts with cell coordinates and never decides the layout on its own: header rows are *candidates* the
user confirms. Markers come from the official help pages (docs/MLA_MERCADOLIVRE_RESEARCH.md): "Obrigatório"
(P2 p.4), "Resumo de erros" (P2 p.4-5), "Código de catálogo ML" (P2 p.2), "Fotos" (P3 p.1), the catalog note
(P2 p.3) and the send-by deadline on the "Ajuda" sheet (P2 p.1-2). The original bytes are never modified.
"""
from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_ZIP_ENTRIES = 5000
SCAN_ROWS = 30          # official captures show titles, headers and instructions at the top of each sheet
PREVIEW_ROWS = 15
PREVIEW_COLS = 60
CELL_TEXT_MAX = 160

MONTHS = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
          "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
_DEADLINE = re.compile(r"ate\s+(?:o\s+dia\s+)?(\d{1,2})\s+de\s+([a-z]+)(?:\s+de\s+(\d{4}))?")

# key -> normalized text that identifies it (substring match on normalized cell text)
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


def find_deadline(text: str, reference: date) -> dict | None:
    """'Faça isso até 10 de setembro' -> day/month; the year is inferred when absent and flagged as such."""
    m = _DEADLINE.search(norm(text))
    if not m or m.group(2) not in MONTHS:
        return None
    day, month = int(m.group(1)), MONTHS[m.group(2)]
    year = int(m.group(3)) if m.group(3) else None
    inferred = year is None
    if inferred:
        # Nearest occurrence not earlier than ~6 months before the upload: a sheet is downloaded shortly
        # before use, so "10 de setembro" seen in November is most likely last September (already expired).
        year = reference.year
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if (candidate - reference).days > 183:
            year -= 1
        elif (reference - candidate).days > 183:
            year += 1
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None
    return {"text": text.strip()[:200], "date": parsed.isoformat(), "year_inferred": inferred}


def inspect_workbook(data: bytes, *, today: date) -> dict:
    """Returns a JSON-serializable report. Raises TemplateRejected for files that cannot be inspected safely."""
    warnings = check_package(data)
    try:
        wb = load_workbook(io.BytesIO(data), read_only=False, data_only=False, keep_vba=False, keep_links=False)
    except Exception as exc:  # openpyxl raises many types for malformed packages
        raise TemplateRejected(f"Não foi possível ler a planilha: {type(exc).__name__}.") from exc

    sheets, deadline = [], None
    help_sheet = next((ws.title for ws in wb.worksheets if norm(ws.title) == "ajuda"), None)
    if help_sheet is None:
        warnings.append('Nenhuma aba "Ajuda" encontrada; a documentação oficial descreve uma (P2 p.1).')

    for index, ws in enumerate(wb.worksheets):
        hits: list[_Hit] = []
        row_fill: dict[int, int] = {}
        row_markers: dict[int, int] = {}
        formulas = 0
        preview = []
        for row in ws.iter_rows(min_row=1, max_row=max(ws.max_row, 1)):
            for cell in row:
                value = cell.value
                if value is None or value == "":
                    continue
                if isinstance(value, str) and value.startswith("="):
                    formulas += 1
                if cell.row > SCAN_ROWS:
                    continue
                row_fill[cell.row] = row_fill.get(cell.row, 0) + 1
                text = norm(value)
                for key, needles in MARKERS.items():
                    if any(n in text for n in needles):
                        hits.append(_Hit(key, cell.coordinate, _cell_text(value)))
                        row_markers[cell.row] = row_markers.get(cell.row, 0) + 1
                if ws.title == help_sheet and deadline is None and isinstance(value, str):
                    found = find_deadline(value, today)
                    if found:
                        deadline = {**found, "sheet": ws.title, "cell": cell.coordinate}
        for r in range(1, min(ws.max_row, PREVIEW_ROWS) + 1):
            preview.append([_cell_text(ws.cell(r, c).value) if ws.cell(r, c).value is not None else ""
                            for c in range(1, min(ws.max_column, PREVIEW_COLS) + 1)])
        validations = [{"sqref": str(dv.sqref), "type": dv.type or "", "formula1": _cell_text(dv.formula1 or ""),
                        "allow_blank": bool(dv.allow_blank)} for dv in ws.data_validations.dataValidation]
        # Header candidates: rows near the top with many filled cells; marker hits raise confidence.
        candidates = sorted(row_fill, key=lambda r: (-(row_fill[r] + 3 * row_markers.get(r, 0)), r))[:3]
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
            "protected": bool(ws.protection.sheet),
            "data_validations": validations[:200],
            "markers": [vars(h) for h in hits][:500],
            "header_candidates": [{"row": r, "filled_cells": row_fill[r], "marker_hits": row_markers.get(r, 0)}
                                  for r in sorted(candidates)],
            "preview": preview,
        })

    return {
        "inspector_version": 1,
        "sheet_count": len(sheets),
        "sheets": sheets,
        "help_sheet": help_sheet,
        "hidden_sheets": [s["name"] for s in sheets if s["state"] != "visible"],
        "defined_names": sorted(list(wb.defined_names.keys()))[:200],
        "workbook_protected": bool(wb.security and wb.security.lockStructure),
        "deadline": deadline,
        "warnings": warnings,
    }


def sheet_columns(report: dict, sheet_name: str, header_row: int) -> list[dict]:
    """Columns of the confirmed header row, from the stored preview (rows 1..PREVIEW_ROWS)."""
    sheet = next((s for s in report.get("sheets", []) if s["name"] == sheet_name), None)
    if sheet is None:
        raise KeyError(sheet_name)
    if not 1 <= header_row <= len(sheet["preview"]):
        raise IndexError(header_row)
    required_cells = {h["cell"] for h in sheet["markers"] if h["key"] == "required"}
    columns = []
    for c, text in enumerate(sheet["preview"][header_row - 1], start=1):
        if not text:
            continue
        letter = get_column_letter(c)
        # "Obrigatório" is shown right below the header in the official captures (P2 p.4, P3 p.4); we only use
        # what is literally in the file: the header cell itself or the cell directly below it.
        required = any(cell in required_cells for cell in (f"{letter}{header_row}", f"{letter}{header_row + 1}"))
        columns.append({"col": letter, "header": text, "required": required})
    return columns
