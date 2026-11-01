"""Compatibility year parsing (e.g. "2010-2015", "até 2014", "2018+"). Compatibilities are never inferred.

Migrated from the discontinued desktop app (src/mla, removed on 2026-11-01); logic unchanged unless noted.
"""
from __future__ import annotations

import re

_YEAR_RE = re.compile(r"(?<!\d)(19\d{2}|20\d{2}|2100)(?!\d)")
_OPEN_END = re.compile(r"(\+|em diante|ou superior|acima|a partir)", re.IGNORECASE)
_UNTIL = re.compile(r"^\s*(at[eé]|ate)\b", re.IGNORECASE)


class CompatibilityError(ValueError):
    pass


def parse_year(text: str) -> int | None:
    text = (text or "").strip()
    if not text:
        return None
    match = _YEAR_RE.fullmatch(text.split(".")[0].strip())  # XLSX numbers arrive as "2015.0"
    if not match:
        raise CompatibilityError(f"Ano inválido: {text!r} (use 4 dígitos, ex.: 2015).")
    return int(match.group(1))


def parse_years(text: str) -> tuple[int | None, int | None]:
    """'2010-2015' / '2010 a 2015' / '2012' / '2018+' / 'até 2014' -> (from, to)."""
    text = (text or "").strip()
    if not text:
        return None, None
    years = [int(y) for y in _YEAR_RE.findall(text)]
    if not years or len(years) > 2:
        raise CompatibilityError(f"Não foi possível ler os anos em {text!r} (ex.: 2010-2015).")
    if len(years) == 2:
        return years[0], years[1]
    if _UNTIL.search(text):
        return None, years[0]
    if _OPEN_END.search(text):
        return years[0], None
    return years[0], years[0]
