"""Builds the data rows of one official sheet (catalog + mapping + adaptive rules) and validates them against the
requirements read from the template itself (layout from the inspector).

Template-derived rules cite the real file analysed on 2026-11-01 (docs/MLA_OFFICIAL_TEMPLATE_ANALYSIS.md):
required columns (row "Obrigatório"), strict lists (data validation with error alert), title length and minimum
price (conditional formatting), variations with the same title and price (Ajuda G52/G55 and price help text),
Gestor URLs pasted within 2 days (Ajuda G45).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from mla_api.domain.adaptive_rules import ActiveRule, apply_rules, is_empty
from mla_api.domain.listing_rules import Issue, ProductData, VariantData, resolve
from mla_api.domain.template_inspector import PLACEHOLDERS, norm

REF_REQUIRED = 'Template: linha "Obrigatório"'
REF_VARIATIONS = "Template: Ajuda G52/G55; ajuda da coluna Preço"
REF_PHOTOS_2_DAYS = "Template: Ajuda G45"


@dataclass
class SheetRow:
    product_id: str
    sku: str
    values: dict[str, object]                 # cells MLA writes {col: value}
    final: dict[str, object]                  # what the row will contain (written or template default)
    applied: list[tuple[str, int]] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


def _header_map(layout: dict) -> dict[str, dict]:
    return {c["col"]: c for c in layout["columns"] if c.get("writable")}


def build_rows(products: list[ProductData], layout: dict, mapping: dict[str, dict],
               rules: list[ActiveRule]) -> list[SheetRow]:
    specs = _header_map(layout)
    variation_cols = set(layout.get("variation_columns") or [])
    rows: list[SheetRow] = []
    for p in products:
        for v in (p.variants or [None]):
            written: dict[str, object] = {}
            for col, spec in specs.items():
                rule = mapping.get(col) or {}
                value = resolve(rule["source"], p, v) if rule.get("source") else ""
                if not str(value).strip() and str(rule.get("default", "")).strip():
                    value = rule["default"]
                if not str(value).strip() and col in variation_cols and v is not None:
                    # "Varia por: Tamanho" receives the variation's own "Tamanho" attribute (Ajuda G57).
                    attr = norm(spec["header"]).split(":", 1)[1].strip()
                    value = next((val for k, val in v.attributes.items() if norm(k) == attr), "")
                if str(value).strip():
                    written[col] = value
            by_header = {spec["header"]: written.get(col, spec.get("default") or "") for col, spec in specs.items()}
            applied = apply_rules(by_header, rules, lambda f, p=p, v=v: resolve(f, p, v))
            for col, spec in specs.items():
                new = applied.values.get(spec["header"])
                old = by_header.get(spec["header"])
                if new != old:
                    written[col] = new
            final = {col: written.get(col, spec.get("default") or "") for col, spec in specs.items()}
            row = SheetRow(p.id, v.sku if v else p.sku, written, final, applied.applied)
            for header in applied.required_missing:
                row.issues.append(Issue("rule_required", "error", "interna", f'"{header}" vazio (regra da empresa).',
                                        "Preencha o dado ou ajuste a regra.", header, "Regra adaptativa", row.sku))
            rows.append(row)
    return rows


def _number(value: object) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def validate_rows(rows: list[SheetRow], layout: dict, products: list[ProductData]) -> None:
    """Adds template issues to each row (in place)."""
    specs = _header_map(layout)
    catalog_sheet = layout.get("catalog_sheet")
    by_id = {p.id: p for p in products}
    for row in rows:
        p = by_id.get(row.product_id)
        uses_catalog = bool(catalog_sheet and p and p.catalog_code)
        for col, spec in specs.items():
            value = row.final.get(col, "")
            empty = is_empty(value)
            label = spec["header"][:60]
            if spec["required"] and empty:
                # With a catalog code the file itself marks some columns as optional (P2 p.3); which ones is known
                # only per row inside Excel, so it is a warning there, an error otherwise.
                sev = "warning" if uses_catalog else "error"
                row.issues.append(Issue("template_required", sev, "template", f'"{label}" é obrigatório e está vazio.',
                                        "Mapeie um campo, defina um valor padrão ou crie uma regra.", col,
                                        REF_REQUIRED, row.sku))
                continue
            if empty:
                continue
            if spec.get("options") and spec.get("strict") and str(value) not in spec["options"]:
                row.issues.append(Issue("template_list", "error", "template",
                                        f'"{value}" não é uma opção aceita em "{label}".',
                                        "Escolha um valor da lista oficial: " +
                                        ", ".join(o for o in spec["options"] if o not in PLACEHOLDERS)[:200],
                                        col, "Template: validação de dados (lista)", row.sku))
            if spec.get("max_length") and len(str(value)) > spec["max_length"]:
                row.issues.append(Issue("template_length", "error", "template",
                                        f'"{label}" tem {len(str(value))} caracteres; o máximo é {spec["max_length"]}.',
                                        "Encurte o texto ou crie uma regra de limite.", col,
                                        "Template: formatação condicional/validação", row.sku))
            if spec.get("kind") == "decimal":
                n = _number(value)
                if n is None:
                    row.issues.append(Issue("template_number", "error", "template", f'"{label}" precisa ser número.',
                                            "Use apenas números.", col, "Template: validação de dados", row.sku))
                elif spec.get("min_value") is not None and n < spec["min_value"]:
                    row.issues.append(Issue("template_min", "error", "template",
                                            f'"{label}" mínimo {spec["min_value"]:.2f}; valor {n:.2f}.',
                                            "Ajuste o valor.", col, "Template: formatação condicional", row.sku))
    # Variations of one product: same title and same price (Ajuda G52/G55, price help text).
    groups: dict[str, list[SheetRow]] = {}
    for row in rows:
        groups.setdefault(row.product_id, []).append(row)
    title_col = next((c for c, s in specs.items() if norm(s["header"]).startswith("titulo")), None)
    price_col = next((c for c, s in specs.items() if norm(s["header"]).startswith("preco")), None)
    for members in groups.values():
        if len(members) < 2:
            continue
        for col, what in ((title_col, "título"), (price_col, "preço")):
            if col and len({str(m.final.get(col, "")) for m in members}) > 1:
                for m in members:
                    m.issues.append(Issue("variation_mismatch", "error", "template",
                                          f"Variações do mesmo produto precisam ter o mesmo {what}.",
                                          f"Use o mesmo {what} em todas as variações.", col, REF_VARIATIONS, m.sku))
    photo_col = next((c for c, s in specs.items() if norm(s["header"]) == "fotos"), None)
    if photo_col and any(str(r.values.get(photo_col, "")).startswith("http") for r in rows):
        rows[0].issues.append(Issue("photos_two_days", "info", "template",
                                    "As URLs do Gestor de fotos devem ser coladas e a planilha enviada em até 2 dias.",
                                    "Gere as URLs perto do envio.", photo_col, REF_PHOTOS_2_DAYS, rows[0].sku))


def variant_of(p: ProductData, sku: str) -> VariantData | None:
    return next((v for v in p.variants if v.sku == sku), None)
