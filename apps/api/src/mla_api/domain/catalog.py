"""Catalog rules: GTIN check digit, SKU format and the completeness rule used by the dashboard.

normalize_gtin / gtin_valid come from the discontinued desktop app (git history before D-030), unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass


def normalize_gtin(text: str) -> str:
    return "".join(ch for ch in (text or "") if ch.isdigit())


def gtin_valid(code: str) -> bool:
    """GTIN-8/12/13/14 check digit (GS1 mod 10)."""
    if len(code) not in (8, 12, 13, 14) or not code.isdigit():
        return False
    digits = [int(ch) for ch in code]
    body, check = digits[:-1], digits[-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def sku_problem(sku: str) -> str | None:
    sku = sku.strip()
    if not sku:
        return "Informe o SKU do produto."
    if any(ch.isspace() for ch in sku):
        return "O SKU não pode conter espaços."
    return None


@dataclass(frozen=True)
class Pending:
    field: str
    message: str
    severity: str  # "error" | "warning" | "info"


def catalog_pendings(*, name: str, brand: str, gtin: str, description: str, price_cents: int | None) -> list[Pending]:
    """Internal catalog completeness, independent of any marketplace.

    Marketplace requirements (category attributes, template columns) are checked later by the template/validation
    engine against confirmed official data; nothing here claims to be a Mercado Livre rule.
    """
    out: list[Pending] = []
    if not name.strip():
        out.append(Pending("name", "Produto sem nome.", "error"))
    if price_cents is None or price_cents <= 0:
        out.append(Pending("price_cents", "Preço de venda não informado.", "error"))
    if not brand.strip():
        out.append(Pending("brand", "Marca não informada.", "warning"))
    if gtin and not gtin_valid(gtin):
        out.append(Pending("gtin", f"GTIN/EAN {gtin} com dígito verificador inválido.", "warning"))
    if not description.strip():
        out.append(Pending("description", "Descrição vazia.", "info"))
    return out


def is_complete(pendings: list[Pending]) -> bool:
    return not any(p.severity in ("error", "warning") for p in pendings)
