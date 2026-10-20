"""Field-level differences between two versions of a master product (for the change history)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mla.core.models import Product
from mla.core.units import format_money

MAX_TEXT = 2000  # long texts are stored up to this size (the history is for tracing, not a backup)

# field, label, kind
TRACKED: tuple[tuple[str, str, str], ...] = (
    ("internal_name", "Nome do produto", "text"), ("commercial_name", "Nome comercial", "text"),
    ("sku", "SKU", "text"), ("title", "Título do anúncio", "text"), ("gtin", "GTIN/EAN", "text"),
    ("manufacturer_code", "Código do fabricante", "text"), ("brand", "Marca", "text"), ("model", "Modelo", "text"),
    ("category", "Categoria", "text"), ("subcategory", "Subcategoria", "text"), ("supplier", "Fornecedor", "text"),
    ("condition", "Condição", "enum"), ("commercial_status", "Status comercial", "enum"),
    ("cost_cents", "Preço de custo", "money"), ("price_cents", "Preço de venda", "money"),
    ("promo_price_cents", "Preço promocional", "money"), ("stock", "Estoque", "int"),
    ("min_stock", "Estoque mínimo", "int"), ("unit", "Unidade de medida", "text"), ("warranty", "Garantia", "text"),
    ("description", "Descrição", "text"), ("technical_description", "Descrição técnica", "text"),
    ("features", "Características", "text"), ("material", "Material", "text"), ("color", "Cor", "text"),
    ("package_contents", "Conteúdo da embalagem", "text"), ("package_type", "Tipo de embalagem", "text"),
    ("weight_g", "Peso (g)", "int"), ("length_mm", "Comprimento (mm)", "int"), ("width_mm", "Largura (mm)", "int"),
    ("height_mm", "Altura (mm)", "int"), ("availability_days", "Prazo de disponibilidade (dias)", "int"),
    ("shipping_notes", "Informações de envio", "text"), ("manufacturer_refs", "Referências de fabricante", "text"),
    ("internal_notes", "Observações internas", "text"),
)


@dataclass
class FieldChange:
    field: str
    label: str
    old: str
    new: str


def _text(value, kind: str) -> str:
    if value is None:
        return ""
    if kind == "money":
        return format_money(value)
    if kind == "enum" and isinstance(value, Enum):
        return getattr(value, "label", str(value.value))
    text = str(value)
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "…"


def _dict_changes(prefix: str, label: str, old: dict[str, str], new: dict[str, str]) -> list[FieldChange]:
    result = []
    for key in sorted(set(old) | set(new), key=str.lower):
        if old.get(key, "") != new.get(key, ""):
            result.append(FieldChange(f"{prefix}:{key}", f"{label}: {key}", old.get(key, ""), new.get(key, "")))
    return result


def _variant_text(v) -> str:
    parts = [v.name or "(sem nome)"]
    if v.price_cents is not None:
        parts.append(format_money(v.price_cents))
    parts.append(f"estoque {v.stock}")
    if v.attributes:
        parts.append(", ".join(f"{k}={val}" for k, val in sorted(v.attributes.items())))
    return " · ".join(parts)


def diff_products(old: Product, new: Product) -> list[FieldChange]:
    """Every user-visible difference, with values formatted as the user reads them."""
    changes: list[FieldChange] = []
    for name, label, kind in TRACKED:
        before, after = getattr(old, name), getattr(new, name)
        if before != after:
            changes.append(FieldChange(name, label, _text(before, kind), _text(after, kind)))
    changes += _dict_changes("spec", "Especificação", old.specs, new.specs)
    changes += _dict_changes("attr", "Atributo", old.custom_attributes, new.custom_attributes)
    old_images = [i.filename for i in old.images]
    new_images = [i.filename for i in new.images]
    if old_images != new_images:
        changes.append(FieldChange("images", "Imagens", f"{len(old_images)} imagem(ns)",
                                   f"{len(new_images)} imagem(ns)"
                                   + (" (ordem ou principal alterada)" if sorted(old_images) == sorted(new_images)
                                      else "")))
    old_files = sorted(f.filename for f in old.files)
    new_files = sorted(f.filename for f in new.files)
    if old_files != new_files:
        changes.append(FieldChange("files", "Arquivos técnicos", f"{len(old_files)} arquivo(s)",
                                   f"{len(new_files)} arquivo(s)"))
    old_variants = {(v.sku or v.name).lower(): v for v in old.variants}
    new_variants = {(v.sku or v.name).lower(): v for v in new.variants}
    for key in sorted(set(old_variants) | set(new_variants)):
        before, after = old_variants.get(key), new_variants.get(key)
        before_text = _variant_text(before) if before else ""
        after_text = _variant_text(after) if after else ""
        if before_text != after_text:
            ref = (after or before).sku or (after or before).name
            changes.append(FieldChange(f"variant:{ref}", f"Variação {ref}", before_text, after_text))
    for marketplace in sorted(set(old.marketplace_data) | set(new.marketplace_data), key=lambda m: m.value):
        before, after = old.marketplace_data.get(marketplace), new.marketplace_data.get(marketplace)
        for name, label, kind in (("enabled", "ativado", "bool"), ("price_cents", "preço", "money"),
                                  ("category_id", "categoria", "text"), ("listing_type", "tipo de anúncio", "text")):
            b = getattr(before, name) if before else None
            a = getattr(after, name) if after else None
            if (b or None) != (a or None):
                fmt = (lambda v: "sim" if v else "não") if kind == "bool" else (lambda v, k=kind: _text(v, k))
                changes.append(FieldChange(f"mp:{marketplace.value}:{name}", f"{marketplace.label}: {label}",
                                           fmt(b), fmt(a)))
        b_attrs = before.attributes if before else {}
        a_attrs = after.attributes if after else {}
        changes += _dict_changes(f"mp:{marketplace.value}:attr", f"{marketplace.label}: atributo", b_attrs, a_attrs)
    return changes
