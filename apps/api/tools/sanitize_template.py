"""Makes a sanitized copy of an official Mercado Livre bulk-listing workbook for local tests.

Replaces, in every XML part, the values that identify the seller: the account/session binding stored in row 1 of
the very hidden sheet(s) and the official store names offered in the "Loja Oficial" lists. Everything else
(sheets, formulas, validations, styles, images) is copied byte for byte. The script prints only counts, never the
replaced values, and refuses to write the output if any original value survives.

The sanitized copy is for MLA's own tests: it is NOT accepted by Mercado Livre (the binding was removed).
Usage: python -I tools/sanitize_template.py <original.xlsx> <sanitized.xlsx>
"""
from __future__ import annotations

import io
import re
import sys
import zipfile
from xml.sax.saxutils import escape

from openpyxl import load_workbook

GENERIC_STORE_CHOICE = "anunciar fora de uma loja oficial"


def _shape(value: str) -> str:
    """Same length/shape, no information: digits -> 0, hex/letters -> a."""
    return re.sub(r"[0-9]", "0", re.sub(r"[A-Za-z]", "a", value))


def sensitive_values(data: bytes) -> dict[str, str]:
    wb = load_workbook(io.BytesIO(data), read_only=False, data_only=True)
    found: dict[str, str] = {}
    for ws in wb.worksheets:
        if ws.sheet_state == "visible":
            continue
        for c in ws[1]:
            if isinstance(c.value, str) and c.value.strip() and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", c.value):
                found[c.value] = _shape(c.value)
    stores = set()
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        for row in ws.iter_rows(min_row=1, max_row=6):
            for c in row:
                if isinstance(c.value, str) and c.value.strip().lower() == "loja oficial":
                    for dv in ws.data_validations.dataValidation:
                        if re.match(rf"^{c.column_letter}\d+", str(dv.sqref)) and dv.formula1:
                            m = re.match(r"^'?([^'!]+)'?!\$?([A-Z]+)\$?(\d+):\$?([A-Z]+)\$?(\d+)$", dv.formula1)
                            if m and m.group(1) in wb.sheetnames:
                                src = wb[m.group(1)]
                                for r in src.iter_rows(min_row=int(m.group(3)), max_row=int(m.group(5))):
                                    stores |= {str(x.value) for x in r if x.value not in (None, "")}
    for n, name in enumerate(sorted(s for s in stores if s.strip().lower() not in (GENERIC_STORE_CHOICE, "selecionar"))):
        found[name] = f"Loja Exemplo {n + 1}"
    return found


def sanitize(data: bytes) -> tuple[bytes, dict[str, int]]:
    values = sensitive_values(data)
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    counts = {"values": len(values), "parts_changed": 0, "replacements": 0}
    with zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            raw = src.read(info)
            if info.filename.endswith((".xml", ".rels")) and values:
                text = raw.decode("utf-8")
                before = text
                for original, fake in values.items():
                    for needle in {original, escape(original)}:
                        counts["replacements"] += text.count(needle)
                        text = text.replace(needle, escape(fake) if needle != original else fake)
                if text != before:
                    counts["parts_changed"] += 1
                    raw = text.encode("utf-8")
            dst.writestr(info, raw, compress_type=info.compress_type)
    result = out.getvalue()
    check = zipfile.ZipFile(io.BytesIO(result))
    for name in check.namelist():
        blob = check.read(name)
        for original in values:
            if original.encode("utf-8") in blob or escape(original).encode("utf-8") in blob:
                raise RuntimeError(f"Valor sensível ainda presente em {name}; cópia não gravada.")
    return result, counts


def main() -> None:
    original, target = sys.argv[1], sys.argv[2]
    result, counts = sanitize(open(original, "rb").read())
    with open(target, "wb") as fh:
        fh.write(result)
    print(f"sanitized: {counts['values']} sensitive values, {counts['replacements']} replacements in "
          f"{counts['parts_changed']} parts -> {target}")


if __name__ == "__main__":
    main()
