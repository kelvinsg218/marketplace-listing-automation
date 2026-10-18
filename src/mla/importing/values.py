"""Turn one mapped source row into typed values for the catalog (or a compatibility).

Values are taken as written: nothing is completed, guessed or corrected beyond
format normalisation (Excel number artefacts, GTIN digits, Brazilian decimals).
Problems are returned per field so the report can show exactly what to fix.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from mla.core.validation import gtin_valid
from mla.core.units import ParseError, parse_money, parse_scaled
from mla.importing.mapping import field_by_key
from mla.services.compatibility import CompatibilityError, parse_year, parse_years

_EXCEL_INT = re.compile(r"^-?\d+\.0+$")
_SCIENTIFIC = re.compile(r"^\d+(?:[.,]\d+)?[eE][+]?\d+$")
_DIMS = re.compile(r"^\s*([\d.,]+)\s*[x×X*]\s*([\d.,]+)\s*[x×X*]\s*([\d.,]+)\s*(cm)?\s*$")
_MEDIA_SPLIT = re.compile(r"\s*[|;\n]\s*")
_MONEY_TEXT = re.compile(r"^(R\$)?\s*-?\s*[\d.,]+$", re.IGNORECASE)
_MEASURE_TEXT = re.compile(r"^-?[\d.,]+\s*(kg|g|gr|cm|mm|m)?$", re.IGNORECASE)
CONDITIONS = {"novo": "new", "new": "new", "n": "new", "usado": "used", "used": "used", "u": "used",
              "seminovo": "used", "recondicionado": "refurbished", "refurbished": "refurbished",
              "remanufaturado": "refurbished"}
COMMERCIAL = {"ativo": "active", "active": "active", "sim": "active", "s": "active", "1": "active", "a": "active",
              "inativo": "inactive", "inactive": "inactive", "nao": "inactive", "não": "inactive", "0": "inactive",
              "i": "inactive", "fora de linha": "discontinued", "descontinuado": "discontinued",
              "discontinued": "discontinued", "fora_de_linha": "discontinued"}
# text fields of the Product model fed directly by a column
TEXT_FIELDS = ("internal_name", "commercial_name", "title", "manufacturer_code", "brand", "model", "category",
               "subcategory", "supplier", "unit", "warranty", "description", "technical_description", "features",
               "material", "color", "package_contents", "manufacturer_refs", "internal_notes", "variant_name",
               "package_type", "shipping_notes", "original_description")


@dataclass
class ParsedRow:
    data: dict[str, Any] = field(default_factory=dict)
    specs: dict[str, str] = field(default_factory=dict)
    attributes: dict[str, str] = field(default_factory=dict)
    images: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    issues: list[dict[str, str]] = field(default_factory=list)

    def error(self, message: str) -> None:
        self.issues.append({"severity": "error", "message": message})

    def warning(self, message: str) -> None:
        self.issues.append({"severity": "warning", "message": message})

    @property
    def has_errors(self) -> bool:
        return any(i["severity"] == "error" for i in self.issues)


_ENTRY_PREFIX = re.compile(r"^(spec|especifica[cç][aã]o|esp|atributo|attr)[_ :.-]+", re.IGNORECASE)


def entry_name(column: str) -> str:
    """Name of a specification/attribute taken from its column ("spec_Voltagem" -> "Voltagem")."""
    return _ENTRY_PREFIX.sub("", column.strip()) or column.strip()


def clean_sku(text: str) -> str:
    value = (text or "").strip().lstrip("'").strip()
    if _EXCEL_INT.match(value):
        value = value.split(".")[0]
    return value


def _integer(text: str, label: str, row: ParsedRow) -> int | None:
    value = text.strip()
    if not value:
        return None
    cleaned = value.replace(".", "").replace(",", ".") if "," in value else value
    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        row.error(f"{label} inválido: {value!r}.")
        return None
    if number != number.to_integral_value():
        row.error(f"{label} precisa ser um número inteiro: {value!r}.")
        return None
    if number < 0:
        row.error(f"{label} negativo: {value!r}.")
        return None
    return int(number)


def _money(text: str, label: str, row: ParsedRow) -> int | None:
    if not _MONEY_TEXT.match(text.strip()):
        row.error(f"{label} inválido: {text.strip()!r}.")
        return None
    try:
        cents = parse_money(text)
    except ParseError:
        row.error(f"{label} inválido: {text.strip()!r}.")
        return None
    if cents is not None and cents < 0:
        row.error(f"{label} negativo: {text.strip()!r}.")
        return None
    return cents


def _scaled(text: str, factor: int, label: str, row: ParsedRow) -> int | None:
    if not _MEASURE_TEXT.match(text.strip()):
        row.error(f"{label} inválido: {text.strip()!r}.")
        return None
    try:
        value = parse_scaled(text, factor)
    except ParseError:
        row.error(f"{label} inválido: {text.strip()!r}.")
        return None
    if value is not None and value < 0:
        row.error(f"{label} negativo: {text.strip()!r}.")
        return None
    return value


def parse_product_row(values: dict[str, str], mapping: dict[str, str]) -> ParsedRow:
    row = ParsedRow()
    for column, key in mapping.items():
        if not key:
            continue
        raw = str(values.get(column) or "")
        text = raw.strip()
        spec = field_by_key("products", key)
        label = spec.label if spec else key
        if key == "spec":
            if text:
                row.specs[entry_name(column)] = text
            continue
        if key == "attr":
            if text:
                row.attributes[entry_name(column)] = text
            continue
        if key == "images":
            row.images += [r for r in _MEDIA_SPLIT.split(text) if r]
            continue
        if key == "files":
            row.files += [r for r in _MEDIA_SPLIT.split(text) if r]
            continue
        if not text:
            continue
        if key in ("sku", "parent_sku"):
            sku = clean_sku(text)
            if any(ch.isspace() for ch in sku):
                row.error(f"{label} com espaços: {sku!r}; corrija na origem.")
            row.data[key] = sku
        elif key == "gtin":
            if _SCIENTIFIC.match(text):
                row.error(f"GTIN/EAN em notação científica ({text}) perdeu dígitos; exporte a coluna como texto.")
                continue
            digits = "".join(ch for ch in text if ch.isdigit())
            if _EXCEL_INT.match(text):
                digits = text.split(".")[0]
            if len(digits) not in (8, 12, 13, 14):
                row.warning(f"GTIN/EAN com {len(digits)} dígitos ({text}); o padrão tem 8, 12, 13 ou 14.")
            elif not gtin_valid(digits):
                row.warning(f"GTIN/EAN {digits} com dígito verificador inválido.")
            row.data["gtin"] = digits
        elif spec and spec.kind == "money":
            row.data[key] = _money(text, label, row)
        elif key in ("stock", "min_stock", "availability_days"):
            row.data[key] = _integer(text, label, row)
        elif key == "weight_kg":
            row.data["weight_g"] = _scaled(text, 1000, label, row)
        elif key == "weight_g":
            row.data["weight_g"] = _scaled(text, 1, label, row)
        elif key in ("length_cm", "width_cm", "height_cm"):
            row.data[key.replace("_cm", "_mm")] = _scaled(text, 10, label, row)
        elif key == "dimensions_cm":
            match = _DIMS.match(text)
            if not match:
                row.error(f"Dimensões ilegíveis: {text!r} (use C x L x A em cm, ex.: 30 x 20 x 10).")
                continue
            for name, part in zip(("length_mm", "width_mm", "height_mm"), match.groups()[:3]):
                row.data[name] = _scaled(part, 10, "Dimensão", row)
        elif key == "condition":
            value = CONDITIONS.get(text.lower())
            if value is None:
                row.error(f"Condição desconhecida: {text!r} (use novo, usado ou recondicionado).")
            else:
                row.data["condition"] = value
        elif key == "commercial_status":
            value = COMMERCIAL.get(text.lower())
            if value is None:
                row.error(f"Status comercial desconhecido: {text!r} (use ativo, inativo ou fora de linha).")
            else:
                row.data["commercial_status"] = value
        elif key in TEXT_FIELDS:
            row.data[key] = raw.strip() if key in ("description", "technical_description", "features",
                                                   "package_contents", "internal_notes", "shipping_notes",
                                                   "original_description") else " ".join(text.split())
    for name in ("weight_g", "length_mm", "width_mm", "height_mm", "cost_cents", "price_cents",
                 "promo_price_cents", "stock", "min_stock", "availability_days"):
        if name in row.data and row.data[name] is None:
            del row.data[name]
    return row


def parse_compat_row(values: dict[str, str], mapping: dict[str, str]) -> ParsedRow:
    row = ParsedRow()
    for column, key in mapping.items():
        if not key:
            continue
        text = str(values.get(column) or "").strip()
        if not text:
            continue
        try:
            if key == "sku":
                row.data["sku"] = clean_sku(text)
            elif key in ("year_from", "year_to"):
                row.data[key] = parse_year(text)
            elif key == "years":
                row.data["year_from"], row.data["year_to"] = parse_years(text)
            else:
                row.data[key] = " ".join(text.split())
        except CompatibilityError as exc:
            row.error(str(exc))
    if not row.data.get("sku"):
        row.error("Linha sem SKU do produto.")
    if not row.data.get("model"):
        row.error("Linha sem modelo compatível.")
    year_from, year_to = row.data.get("year_from"), row.data.get("year_to")
    if year_from and year_to and year_from > year_to:
        row.error(f"Ano inicial {year_from} maior que o final {year_to}.")
    return row
