"""Adaptive rules (versioned, scoped) and the Assistente de Correção (error summary -> proposals).

Flow: interpret (sentence) or form -> simulate (before/after + official conflicts + rule conflicts) -> create
(explicit approval) -> applied on validation/export. Every content change creates a new version; revert creates a
new version copying an old one, so history is never overwritten.
"""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from mla_api import audit
from mla_api.deps import OrgContext, require
from mla_api.domain.adaptive_rules import (OPERATIONS, ActiveRule, RuleInvalid, conflicts, interpret,
                                           official_conflict, parse_error_summary, validate_definition)
from mla_api.domain.listing_rules import SOURCE_FIELDS, suggest_source
from mla_api.domain.sheet_builder import build_rows
from mla_api.models import (ListingBatch, ListingBatchItem, ListingRule, ListingRuleVersion, MarketplaceTemplate,
                            Product, ProductVariant, SellerAccount, TemplateMapping)
from mla_api.schemas import UtcDatetime
from mla_api.services.listing_data import load_products
from mla_api.services.rules_service import rules_for_batch

router = APIRouter(prefix="/api/orgs/{org_id}", tags=["adaptive-rules"])
Scope = Literal["organization", "account", "category", "template", "batch"]
SIMULATION_ROWS = 20


def _source_fields() -> set[str]:
    return set(SOURCE_FIELDS)


def _batch(ctx: OrgContext, batch_id: uuid.UUID) -> ListingBatch:
    b = ctx.db.scalar(select(ListingBatch).where(ListingBatch.id == batch_id,
                                                 ListingBatch.organization_id == ctx.org_id))
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lote não encontrado.")
    return b


def _sheet_layout(ctx: OrgContext, b: ListingBatch) -> tuple[MarketplaceTemplate, dict] | None:
    if not b.template_id or not b.sheet_name:
        return None
    t = ctx.db.scalar(select(MarketplaceTemplate).where(MarketplaceTemplate.id == b.template_id,
                                                        MarketplaceTemplate.organization_id == ctx.org_id))
    sheet = next((s for s in (t.structure or {}).get("sheets", []) if s["name"] == b.sheet_name), None) if t else None
    layout = (sheet or {}).get("layout")
    return (t, layout) if layout and layout.get("data_start_row") else None


def _attributes(ctx: OrgContext) -> list[str]:
    """Catalog attribute names of the organization (custom attributes + variation attributes)."""
    names: set[str] = set()
    for attrs in ctx.db.scalars(select(Product.attributes).where(Product.organization_id == ctx.org_id).limit(2000)):
        names |= set((attrs or {}).keys())
    for attrs in ctx.db.scalars(select(ProductVariant.attributes)
                                .where(ProductVariant.organization_id == ctx.org_id).limit(2000)):
        names |= set((attrs or {}).keys())
    return sorted(n for n in names if 0 < len(n) <= 60)


def _check_scope(ctx: OrgContext, scope: str, ref: str) -> str:
    """Scope references must belong to the organization. System-wide rules are not available to clients."""
    model = {"account": SellerAccount, "template": MarketplaceTemplate, "batch": ListingBatch}.get(scope)
    if scope == "organization":
        return ""
    if scope == "category":
        if not ref.strip() or len(ref) > 64:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Informe a categoria (nome da aba).")
        return ref.strip()
    try:
        rid = uuid.UUID(ref)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Referência de escopo inválida.")
    if not ctx.db.scalar(select(model.id).where(model.id == rid, model.organization_id == ctx.org_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Referência de escopo não encontrada.")
    return str(rid)


# --- schemas ------------------------------------------------------------------------------------------------------
class RuleDefIn(BaseModel):
    target: str = Field(min_length=1, max_length=200)
    operation: str
    params: dict = Field(default_factory=dict)
    condition: dict = Field(default_factory=lambda: {"when": "always"})


class SimulateIn(BaseModel):
    batch_id: uuid.UUID
    definition: RuleDefIn
    scope: Scope = "batch"
    scope_ref: str = ""


class RuleIn(SimulateIn):
    name: str = Field(min_length=1, max_length=120)
    priority: int = Field(default=100, ge=0, le=1000)
    origin: Literal["manual", "prompt", "erro"] = "manual"
    origin_text: str = Field(default="", max_length=2000)
    approved: bool = False


class RulePatch(BaseModel):
    definition: RuleDefIn | None = None
    priority: int | None = Field(default=None, ge=0, le=1000)
    status: Literal["active", "inactive"] | None = None
    note: str = Field(default="", max_length=300)


class RuleOut(BaseModel):
    id: uuid.UUID
    name: str
    scope: str
    scope_ref: str
    priority: int
    status: str
    version: int
    definition: dict
    origin: str
    origin_text: str
    created_at: UtcDatetime
    updated_at: UtcDatetime


class VersionOut(BaseModel):
    version: int
    definition: dict
    note: str
    author: str | None
    created_at: UtcDatetime


def _out(r: ListingRule, v: ListingRuleVersion) -> RuleOut:
    return RuleOut(id=r.id, name=r.name, scope=r.scope, scope_ref=r.scope_ref, priority=r.priority, status=r.status,
                   version=r.current_version, definition=v.definition, origin=r.origin, origin_text=r.origin_text,
                   created_at=r.created_at, updated_at=r.updated_at)


def _current(ctx: OrgContext, r: ListingRule) -> ListingRuleVersion:
    return ctx.db.scalar(select(ListingRuleVersion).where(ListingRuleVersion.rule_id == r.id,
                                                          ListingRuleVersion.version == r.current_version))


def _rule(ctx: OrgContext, rule_id: uuid.UUID) -> ListingRule:
    r = ctx.db.scalar(select(ListingRule).where(ListingRule.id == rule_id, ListingRule.organization_id == ctx.org_id))
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Regra não encontrada.")
    return r


def _validate(raw: RuleDefIn):
    try:
        return validate_definition(raw.model_dump(), _source_fields())
    except RuleInvalid as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


# --- simulation ---------------------------------------------------------------------------------------------------
@router.post("/rules/simulate")
def simulate(body: SimulateIn, ctx: OrgContext = Depends(require("catalog.read"))) -> dict:
    """Before/after on the batch's rows, the official-requirement check and conflicts. Writes nothing."""
    b = _batch(ctx, body.batch_id)
    d = _validate(body.definition)
    found = _sheet_layout(ctx, b)
    if not found:
        raise HTTPException(status.HTTP_409_CONFLICT, "O lote precisa de template e aba com a estrutura oficial.")
    t, layout = found
    spec = next((c for c in layout["columns"] if c["header"].strip().lower() == d.target.strip().lower()), None)
    official = official_conflict(d, spec)
    existing = [{"name": r.name, "scope": r.scope, "scope_ref": r.scope_ref, "definition": v.definition}
                for r, v in ctx.db.execute(select(ListingRule, ListingRuleVersion).join(
                    ListingRuleVersion, (ListingRuleVersion.rule_id == ListingRule.id)
                    & (ListingRuleVersion.version == ListingRule.current_version))
                    .where(ListingRule.organization_id == ctx.org_id, ListingRule.status == "active")).all()]
    ref = body.scope_ref if body.scope != "batch" else str(b.id)
    found_conflicts = conflicts(d, body.scope, ref, existing)
    ids = list(ctx.db.scalars(select(ListingBatchItem.product_id).where(ListingBatchItem.batch_id == b.id)
                              .limit(SIMULATION_ROWS)))
    products = load_products(ctx.db, ctx.org_id, ids)
    m = ctx.db.scalar(select(TemplateMapping).where(TemplateMapping.template_id == t.id,
                                                    TemplateMapping.organization_id == ctx.org_id,
                                                    TemplateMapping.sheet_name == b.sheet_name))
    mapping = m.rules if m else {}
    current_rules = rules_for_batch(ctx.db, ctx.org_id, b)
    before = build_rows(products, layout, mapping, current_rules)
    after = build_rows(products, layout, mapping, current_rules + [ActiveRule("nova", 0, body.scope, 10**6, d)])
    col = spec["col"] if spec else None
    changes = []
    for x, y in zip(before, after):
        old, new = (x.final.get(col, ""), y.final.get(col, "")) if col else ("", "")
        changes.append({"sku": x.sku, "before": str(old), "after": str(new), "changed": old != new})
    return {"definition": d.as_dict(), "official_conflict": official, "conflicts": found_conflicts,
            "column": col, "rows": changes[:SIMULATION_ROWS],
            "changed": sum(c["changed"] for c in changes), "can_apply": official is None}


# --- CRUD ---------------------------------------------------------------------------------------------------------
@router.get("/rules", response_model=list[RuleOut])
def list_rules(ctx: OrgContext = Depends(require("catalog.read")), scope: Scope | None = None) -> list[RuleOut]:
    q = select(ListingRule, ListingRuleVersion).join(
        ListingRuleVersion, (ListingRuleVersion.rule_id == ListingRule.id)
        & (ListingRuleVersion.version == ListingRule.current_version)).where(
        ListingRule.organization_id == ctx.org_id)
    if scope:
        q = q.where(ListingRule.scope == scope)
    return [_out(r, v) for r, v in ctx.db.execute(q.order_by(ListingRule.updated_at.desc())).all()]


@router.post("/rules", response_model=RuleOut, status_code=201)
def create_rule(body: RuleIn, ctx: OrgContext = Depends(require("catalog.write"))) -> RuleOut:
    if not body.approved:
        raise HTTPException(status.HTTP_409_CONFLICT, "Revise a simulação e aprove a regra antes de salvar.")
    sim = simulate(SimulateIn(batch_id=body.batch_id, definition=body.definition, scope=body.scope,
                              scope_ref=body.scope_ref), ctx)
    if sim["official_conflict"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Conflito com exigência oficial: " + sim["official_conflict"])
    ref = str(body.batch_id) if body.scope == "batch" else _check_scope(ctx, body.scope, body.scope_ref)
    r = ListingRule(organization_id=ctx.org_id, name=body.name.strip(), scope=body.scope, scope_ref=ref,
                    priority=body.priority, status="active", current_version=1, origin=body.origin,
                    origin_text=body.origin_text, created_by=ctx.user.id)
    ctx.db.add(r)
    ctx.db.flush()
    v = ListingRuleVersion(organization_id=ctx.org_id, rule_id=r.id, version=1, definition=sim["definition"],
                           note="criação", author_id=ctx.user.id)
    ctx.db.add(v)
    audit.record(ctx.db, "rule.created", user_id=ctx.user.id, org_id=ctx.org_id, target_type="rule",
                 target_id=r.id, scope=body.scope, origin=body.origin)
    ctx.db.commit()
    return _out(r, v)


@router.patch("/rules/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: uuid.UUID, body: RulePatch, ctx: OrgContext = Depends(require("catalog.write"))) -> RuleOut:
    r = _rule(ctx, rule_id)
    if body.definition is not None:
        d = _validate(body.definition)
        r.current_version += 1
        ctx.db.add(ListingRuleVersion(organization_id=ctx.org_id, rule_id=r.id, version=r.current_version,
                                      definition=d.as_dict(), note=body.note or "edição", author_id=ctx.user.id))
    if body.priority is not None:
        r.priority = body.priority
    if body.status is not None:
        r.status = body.status
    audit.record(ctx.db, "rule.updated", user_id=ctx.user.id, org_id=ctx.org_id, target_type="rule",
                 target_id=r.id, version=r.current_version, status=r.status)
    ctx.db.commit()
    return _out(r, _current(ctx, r))


@router.get("/rules/{rule_id}/versions", response_model=list[VersionOut])
def versions(rule_id: uuid.UUID, ctx: OrgContext = Depends(require("catalog.read"))) -> list[VersionOut]:
    from mla_api.models import User
    r = _rule(ctx, rule_id)
    rows = ctx.db.execute(select(ListingRuleVersion, User.name).outerjoin(User, User.id == ListingRuleVersion.author_id)
                          .where(ListingRuleVersion.rule_id == r.id).order_by(ListingRuleVersion.version.desc())).all()
    return [VersionOut(version=v.version, definition=v.definition, note=v.note, author=name, created_at=v.created_at)
            for v, name in rows]


class RevertIn(BaseModel):
    version: int = Field(ge=1)


@router.post("/rules/{rule_id}/revert", response_model=RuleOut)
def revert(rule_id: uuid.UUID, body: RevertIn, ctx: OrgContext = Depends(require("catalog.write"))) -> RuleOut:
    r = _rule(ctx, rule_id)
    old = ctx.db.scalar(select(ListingRuleVersion).where(ListingRuleVersion.rule_id == r.id,
                                                         ListingRuleVersion.version == body.version))
    if old is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Versão não encontrada.")
    r.current_version += 1
    v = ListingRuleVersion(organization_id=ctx.org_id, rule_id=r.id, version=r.current_version,
                           definition=old.definition, note=f"reversão para v{body.version}", author_id=ctx.user.id)
    ctx.db.add(v)
    audit.record(ctx.db, "rule.reverted", user_id=ctx.user.id, org_id=ctx.org_id, target_type="rule",
                 target_id=r.id, to=body.version)
    ctx.db.commit()
    return _out(r, v)


# --- natural language + Assistente de Correção ------------------------------------------------------------------
class InterpretIn(BaseModel):
    batch_id: uuid.UUID
    text: str = Field(min_length=3, max_length=2000)


@router.post("/rules/interpret")
def interpret_request(body: InterpretIn, ctx: OrgContext = Depends(require("catalog.read"))) -> dict:
    """Deterministic interpretation (no external AI). Returns a proposal and questions; saves nothing."""
    b = _batch(ctx, body.batch_id)
    found = _sheet_layout(ctx, b)
    if not found:
        raise HTTPException(status.HTTP_409_CONFLICT, "O lote precisa de template e aba com a estrutura oficial.")
    _, layout = found
    headers = [c["header"] for c in layout["columns"] if c.get("writable")]
    p = interpret(body.text, headers, _attributes(ctx))
    out = {"definition": p.definition, "scope": p.scope, "scope_ref": b.sheet_name if p.scope == "category" else "",
           "explanation": p.explanation, "questions": p.questions, "confidence": p.confidence,
           "engine": "interpretação determinística (sem IA externa)", "operations": OPERATIONS}
    if p.definition:
        try:
            out["simulation"] = simulate(SimulateIn(batch_id=b.id, definition=RuleDefIn(**p.definition),
                                                    scope=p.scope, scope_ref=out["scope_ref"]), ctx)
        except HTTPException as exc:
            out["questions"].append(str(exc.detail))
            out["definition"] = None
    return out


class ErrorSummaryIn(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


@router.post("/batches/{batch_id}/error-summary")
def analyze_error_summary(batch_id: uuid.UUID, body: ErrorSummaryIn,
                          ctx: OrgContext = Depends(require("catalog.read"))) -> dict:
    """Reads a pasted "Resumo de erros" (one item per line, e.g. "- Marca") and proposes deterministic fixes.
    Unknown items are reported as such; nothing is diagnosed beyond what the text says."""
    b = _batch(ctx, batch_id)
    found = _sheet_layout(ctx, b)
    if not found:
        raise HTTPException(status.HTTP_409_CONFLICT, "O lote precisa de template e aba com a estrutura oficial.")
    _, layout = found
    specs = {c["header"]: c for c in layout["columns"] if c.get("writable")}
    items = []
    for item in parse_error_summary(body.text, list(specs)):
        spec = specs.get(item["column"]) if item["column"] else None
        proposals = []
        if spec:
            field = suggest_source(spec["header"])
            if field:
                proposals.append({"label": f'Preencher "{spec["header"]}" com o campo "{SOURCE_FIELDS[field]}" do catálogo',
                                  "definition": {"target": spec["header"], "operation": "copy_field",
                                                 "params": {"field": field}, "condition": {"when": "target_empty"}}})
            proposals.append({"label": f'Usar um valor padrão em "{spec["header"]}" quando estiver vazio',
                              "definition": {"target": spec["header"], "operation": "default_if_empty",
                                             "params": {"value": ""}, "condition": {"when": "always"}},
                              "needs_value": True, "options": [o for o in (spec.get("options") or [])
                                                               if o not in ("Selecionar", "Insira ou selecione um valor")]})
        items.append({**item, "required": bool(spec and spec["required"]), "proposals": proposals,
                      "message": None if spec else "Não reconheci este item como coluna da aba; descreva o erro com "
                                                   "mais detalhes ou informe a coluna."})
    return {"items": items, "sheet": b.sheet_name}
