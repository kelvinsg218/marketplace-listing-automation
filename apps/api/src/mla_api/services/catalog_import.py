"""Catalog import (Central de Importações): file -> parsed rows -> plan (dry run) -> commit in chunks.

Built on the migrated parsers (mla_api.importing). Rules:
- Nothing is invented: only mapped, non-empty cells reach the catalog; unknown columns are offered as custom
  attributes, never silently dropped (the user decides in the mapping).
- An existing SKU is updated only with the explicit option `update_existing`, and only with the fields the file
  fills that differ (never erasing data). Duplicate SKUs inside the same file: first one wins, the rest are errors.
- Image URLs found in the client's file are kept as *external* references (attribute), never as Gestor URLs.
- Every query is scoped to the organization; processing runs in chunks and honours cancellation between chunks.
"""
from __future__ import annotations

import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from mla_api.importing.mapping import PRODUCT_FIELDS, field_by_key
from mla_api.importing.readers import Source, open_source
from mla_api.importing.values import parse_product_row
from mla_api.models import Product, ProductVariant

ALLOWED_FORMATS = ("csv", "xlsx", "json", "xml")
MAX_IMPORT_BYTES = 50 * 1024 * 1024
CHUNK = 200
REPORT_LIMIT = 500
EXTERNAL_IMAGES_ATTR = "Imagens da base (URLs externas)"
NAME_KEYS = ("internal_name", "title", "commercial_name")
CORE = {"sku", "parent_sku", "gtin", "brand", "model", "description", "price_cents", "cost_cents", "stock",
        *NAME_KEYS}
VARIANT_ATTR_KEYS = {"color": "Cor", "size": "Tamanho", "variant_name": "Variação"}


def target_fields() -> list[dict]:
    """Fields the user can map a column to (catalog fields + custom attribute + ignore)."""
    return [{"key": f.key, "label": f.label, "group": f.group} for f in PRODUCT_FIELDS if f.key != "files"]


def open_from_bytes(data: bytes, filename: str, sheet: str | None = None) -> tuple[Source, Path]:
    """Parsers read from disk: write a private temp copy (caller deletes the directory)."""
    tmpdir = Path(tempfile.mkdtemp(prefix="mla-import-"))
    path = tmpdir / ("upload" + Path(filename).suffix.lower())
    path.write_bytes(data)
    return open_source(path, sheet=sheet or None), tmpdir


@dataclass
class RowPlan:
    number: int
    where: str
    sku: str
    action: str                      # create | update | unchanged | variant | skip | error
    changes: list[str] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)


def _product_values(parsed) -> dict:
    data = parsed.data
    values: dict = {}
    name = next((data[k] for k in NAME_KEYS if data.get(k)), None)
    if name:
        values["name"] = str(name)[:200]
    for key in ("brand", "model", "gtin", "description"):
        if data.get(key):
            values[key] = str(data[key])
    for key in ("price_cents", "cost_cents", "stock"):
        if data.get(key) is not None:
            values[key] = data[key]
    attrs: dict[str, str] = {}
    for key, value in data.items():
        if key in CORE or value in (None, "") or key in VARIANT_ATTR_KEYS:
            continue
        spec = field_by_key("products", key)
        attrs[spec.label if spec else key] = str(value)
    attrs.update({k: str(v) for k, v in parsed.specs.items()})
    attrs.update({k: str(v) for k, v in parsed.attributes.items()})
    external = [u for u in parsed.images if u.lower().startswith(("http://", "https://"))]
    if external:
        attrs[EXTERNAL_IMAGES_ATTR] = ",".join(external)
    if attrs:
        values["attributes"] = attrs
    return values


def plan_rows(db: Session, org_id: uuid.UUID, source: Source, mapping: dict[str, str], update_existing: bool,
              cancelled=lambda: False):
    """Yields RowPlan per row plus the values to write. Pure read: nothing is written here."""
    seen: set[str] = set()
    existing: dict[str, Product] = {}
    batch: list = []

    def flush():
        skus = [p.data.get("sku") for _, p in batch if p.data.get("sku")]
        if skus:
            for prod in db.scalars(select(Product).where(Product.organization_id == org_id, Product.sku.in_(skus))):
                existing[prod.sku] = prod
        out = []
        for row, parsed in batch:
            out.append(_plan_one(row, parsed, existing, seen, update_existing))
        batch.clear()
        return out

    for row in source.rows():
        batch.append((row, parse_product_row(row.values, mapping)))
        if len(batch) >= CHUNK:
            yield from flush()
            if cancelled():
                return
    yield from flush()


def _plan_one(row, parsed, existing, seen, update_existing):
    sku = str(parsed.data.get("sku") or "").strip()
    plan = RowPlan(row.number, row.where, sku, "error", issues=list(parsed.issues))
    if row.review:
        plan.issues.append({"severity": "warning", "message": row.review})
    if not sku:
        plan.issues.append({"severity": "error", "message": "Linha sem SKU."})
        return plan, None
    if parsed.has_errors:
        return plan, None
    if sku in seen:
        plan.issues.append({"severity": "error", "message": f"SKU {sku} repetido no arquivo; só a primeira linha vale."})
        return plan, None
    seen.add(sku)
    values = _product_values(parsed)
    parent = str(parsed.data.get("parent_sku") or "").strip()
    if parent and parent != sku:
        plan.action = "variant"
        attrs = {label: str(parsed.data[k]) for k, label in VARIANT_ATTR_KEYS.items() if parsed.data.get(k)}
        if not attrs:
            plan.action = "error"
            plan.issues.append({"severity": "error", "message": "Variação sem cor, tamanho ou nome da variação."})
            return plan, None
        return plan, {"variant_of": parent, "sku": sku, "attributes": attrs, "gtin": values.get("gtin", ""),
                      "stock": values.get("stock", 0), "price_cents": values.get("price_cents")}
    current = existing.get(sku)
    if current is None:
        if not values.get("name"):
            plan.issues.append({"severity": "error", "message": "Produto novo sem nome."})
            return plan, None
        plan.action = "create"
        return plan, values
    if not update_existing:
        plan.action = "skip"
        plan.issues.append({"severity": "info", "message": "SKU já existe no catálogo; atualização desativada."})
        return plan, None
    changes = {}
    for key, value in values.items():
        if key == "attributes":
            merged = {**(current.attributes or {}), **value}
            if merged != (current.attributes or {}):
                changes["attributes"] = merged
        elif getattr(current, key) != value:
            changes[key] = value
    plan.action = "update" if changes else "unchanged"
    plan.changes = sorted(changes)
    return plan, changes or None


def commit_plan(db: Session, org_id: uuid.UUID, items) -> dict:
    """Writes one chunk of planned rows (one transaction per chunk). Returns counters."""
    counts = {"created": 0, "updated": 0, "variants": 0}
    by_sku: dict[str, Product] = {}
    for plan, values in items:
        if plan.action == "create":
            p = Product(organization_id=org_id, sku=plan.sku, name=values["name"], brand=values.get("brand", ""),
                        model=values.get("model", ""), gtin=values.get("gtin", ""),
                        description=values.get("description", ""), price_cents=values.get("price_cents"),
                        cost_cents=values.get("cost_cents"), stock=values.get("stock", 0) or 0,
                        attributes=values.get("attributes", {}))
            db.add(p)
            by_sku[plan.sku] = p
            counts["created"] += 1
        elif plan.action == "update":
            p = db.scalar(select(Product).where(Product.organization_id == org_id, Product.sku == plan.sku))
            for key, value in values.items():
                setattr(p, key, value)
            counts["updated"] += 1
    db.flush()
    for plan, values in items:
        if plan.action != "variant":
            continue
        parent = by_sku.get(values["variant_of"]) or db.scalar(
            select(Product).where(Product.organization_id == org_id, Product.sku == values["variant_of"]))
        taken = db.scalar(select(ProductVariant.id).where(ProductVariant.organization_id == org_id,
                                                          ProductVariant.sku == plan.sku)) or \
            db.scalar(select(Product.id).where(Product.organization_id == org_id, Product.sku == plan.sku))
        if parent is None or taken:
            plan.action = "error"
            plan.issues.append({"severity": "error", "message": "Produto pai não encontrado." if parent is None
                                else f"SKU {plan.sku} já existe."})
            continue
        db.add(ProductVariant(organization_id=org_id, product_id=parent.id, sku=plan.sku,
                              attributes=values["attributes"], gtin=values["gtin"] or "",
                              price_cents=values["price_cents"], stock=values["stock"] or 0))
        counts["variants"] += 1
    return counts
