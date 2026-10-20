"""Parsing and formatting of Brazilian money and measures.

Money is stored as integer cents, weight as integer grams and dimensions as
integer millimetres, so no floating point reaches the database.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_NUMBER_RE = re.compile(r"[^\d,.\-]")


class ParseError(ValueError):
    pass


def _to_decimal(text: str) -> Decimal | None:
    cleaned = _NUMBER_RE.sub("", (text or "").strip())
    if not cleaned:
        return None
    if "," in cleaned:
        # Brazilian format: "." groups thousands, "," is the decimal separator
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ParseError(f"Número inválido: {text!r}") from exc


def parse_money(text: str) -> int | None:
    """'R$ 1.234,56' -> 123456 cents. Empty -> None."""
    value = _to_decimal(text)
    if value is None:
        return None
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


_MONEY_STRICT = re.compile(r"^\s*(R\$)?\s*-?\s*[\d.,]*\s*$", re.IGNORECASE)


def parse_money_strict(text: str) -> int | None:
    """Like parse_money, but refuses stray letters ("12,3x" is an error, not R$ 12,30)."""
    if (text or "").strip() and not _MONEY_STRICT.match(text):
        raise ParseError(f"Valor em reais inválido: {text.strip()!r}")
    return parse_money(text)


def format_money(cents: int | None, symbol: bool = True) -> str:
    if cents is None:
        return ""
    negative = cents < 0
    whole, frac = divmod(abs(cents), 100)
    text = f"{whole:,}".replace(",", ".") + f",{frac:02d}"
    if negative:
        text = "-" + text
    return f"R$ {text}" if symbol else text


def parse_scaled(text: str, factor: int) -> int | None:
    """Parse a decimal string and multiply by factor ('20,5' cm, factor 10 -> 205 mm)."""
    value = _to_decimal(text)
    if value is None:
        return None
    return int((value * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_scaled(value: int | None, factor: int) -> str:
    if value is None:
        return ""
    quotient = Decimal(value) / Decimal(factor)
    text = f"{quotient.normalize():f}"
    return text.replace(".", ",")
