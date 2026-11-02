"""Internal categories, automatic classification, review queue and manual confirmation."""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from mla_api import audit
from mla_api.deps import OrgContext, require
from mla_api.domain.classifier import DEFAULT_TREE, CategoryRule, classify
from mla_api.models import Category, Product, ProductClassification

router = APIRouter(prefix="/api/orgs/{org_id}", tags=["categories"])
CHUNK = 500


class Keywords(BaseModel):
    phrases: list[str] = Field(default_factory=list, max_length=200)
    words: list[str] = Field(default_factory=list, max_length=200)
    exclude: list[str] = Field(default_factory=list, max_length=200)


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    parent_id: uuid.UUID | None = None
    keywords: Keywords = Field(default_factory=Keywords)
    ml_category_id: str = Field(default="", max_length=40, pattern=r"^[A-Za-z0-9]*$")
    ml_category_confirmed: bool = False


def _clean_terms(values: list[str]) -> list[str]:
    out = []
    for v in values:
        v = " ".join(str(v).split())[:80]
        if v and v.lower() not in [x.lower() for x in out]:
            out.append(v)
    return out


def _cats(ctx: OrgContext) -> list[Category]:
    return list(ctx.db.scalars(select(Category).where(Category.organization_id == ctx.org_id)))


def _paths(cats: list[Category]) -> dict[uuid.UUID, str]:
    by_id = {c.id: c for c in cats}

    def path(c: Category) -> str:
        parts, seen = [c.name], {c.id}
        while c.parent_id and c.parent_id in by_id and c.parent_id not in seen:
            c = by_id[c.parent_id]
            seen.add(c.id)
            parts.append(c.name)
        return " > ".join(reversed(parts))
    return {c.id: path(c) for c in cats}


def _out(c: Category, paths: dict, counts: dict | None = None) -> dict:
    return {"id": str(c.id), "name": c.name, "parent_id": str(c.parent_id) if c.parent_id else None,
            "path": paths.get(c.id, c.name), "keywords": c.keywords or {}, "ml_category_id": c.ml_category_id,
            "ml_category_confirmed": c.ml_category_confirmed, "products": (counts or {}).get(c.id, 0)}


@router.get("/categories")
def list_categories(ctx: OrgContext = Depends(require("catalog.read"))) -> list[dict]:
    cats = _cats(ctx)
    paths = _paths(cats)
    counts = dict(ctx.db.execute(select(ProductClassification.category_id, func.count())
                                 .where(ProductClassification.organization_id == ctx.org_id,
                                        ProductClassification.status == "confirmed")
                                 .group_by(ProductClassification.category_id)).all())
    return sorted((_out(c, paths, counts) for c in cats), key=lambda x: x["path"])


def _category(ctx: OrgContext, cid: uuid.UUID) -> Category:
    c = ctx.db.scalar(select(Category).where(Category.id == cid, Category.organization_id == ctx.org_id))
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Categoria não encontrada.")
    return c


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, ctx: OrgContext = Depends(require("catalog.write"))) -> dict:
    if body.parent_id:
        _category(ctx, body.parent_id)
    c = Category(organization_id=ctx.org_id, parent_id=body.parent_id, name=body.name.strip(),
                 keywords={k: _clean_terms(v) for k, v in body.keywords.model_dump().items()},
                 ml_category_id=body.ml_category_id, ml_category_confirmed=body.ml_category_confirmed)
    ctx.db.add(c)
    try:
        ctx.db.flush()
    except IntegrityError:
        ctx.db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma categoria com este nome neste nível.")
    audit.record(ctx.db, "category.created", user_id=ctx.user.id, org_id=ctx.org_id, target_type="category",
                 target_id=c.id, name=c.name)
    ctx.db.commit()
    return _out(c, _paths(_cats(ctx)))


@router.put("/categories/{category_id}")
def update_category(category_id: uuid.UUID, body: CategoryIn,
                    ctx: OrgContext = Depends(require("catalog.write"))) -> dict:
    c = _category(ctx, category_id)
    before = c.keywords
    c.name = body.name.strip()
    c.keywords = {k: _clean_terms(v) for k, v in body.keywords.model_dump().items()}
    c.ml_category_id, c.ml_category_confirmed = body.ml_category_id, body.ml_category_confirmed and bool(body.ml_category_id)
    # Keyword changes are audited with the previous value, so a rule can be reverted.
    audit.record(ctx.db, "category.updated", user_id=ctx.user.id, org_id=ctx.org_id, target_type="category",
                 target_id=c.id, previous_keywords=before, keywords=c.keywords)
    ctx.db.commit()
    return _out(c, _paths(_cats(ctx)))


@router.delete("/categories/{category_id}", status_code=204, response_class=Response, response_model=None)
def delete_category(category_id: uuid.UUID, ctx: OrgContext = Depends(require("catalog.write"))) -> None:
    c = _category(ctx, category_id)
    audit.record(ctx.db, "category.deleted", user_id=ctx.user.id, org_id=ctx.org_id, target_type="category",
                 target_id=c.id, name=c.name)
    ctx.db.delete(c)
    ctx.db.commit()


@router.post("/categories/seed-defaults")
def seed_defaults(ctx: OrgContext = Depends(require("catalog.write"))) -> dict:
    """Creates the example tree only where names do not exist yet (idempotent)."""
    created = 0
    existing = {(c.parent_id, c.name) for c in _cats(ctx)}
    for top, children in DEFAULT_TREE.items():
        parent = ctx.db.scalar(select(Category).where(Category.organization_id == ctx.org_id,
                                                      Category.parent_id.is_(None), Category.name == top))
        if parent is None:
            parent = Category(organization_id=ctx.org_id, name=top, keywords={})
            ctx.db.add(parent)
            ctx.db.flush()
            created += 1
        for name, kw in children.items():
            if (parent.id, name) not in existing:
                ctx.db.add(Category(organization_id=ctx.org_id, parent_id=parent.id, name=name,
                                    keywords={"phrases": kw.get("phrases", []), "words": kw.get("words", []),
                                              "exclude": kw.get("exclude", [])}))
                created += 1
    ctx.db.commit()
    return {"created": created}


def _rules(ctx: OrgContext) -> list[CategoryRule]:
    cats = _cats(ctx)
    paths = _paths(cats)
    return [CategoryRule(str(c.id), paths[c.id], tuple((c.keywords or {}).get("phrases", [])),
                         tuple((c.keywords or {}).get("words", [])), tuple((c.keywords or {}).get("exclude", [])))
            for c in cats if (c.keywords or {}).get("phrases") or (c.keywords or {}).get("words")]


class RunIn(BaseModel):
    product_ids: list[uuid.UUID] | None = Field(default=None, max_length=50_000)


@router.post("/classification/run")
def run_classification(body: RunIn, ctx: OrgContext = Depends(require("catalog.write"))) -> dict:
    """Suggests categories. Confirmed (manual) classifications are never touched."""
    rules = _rules(ctx)
    if not rules:
        raise HTTPException(status.HTTP_409_CONFLICT, "Crie categorias com palavras-chave antes de classificar.")
    confirmed = set(ctx.db.scalars(select(ProductClassification.product_id).where(
        ProductClassification.organization_id == ctx.org_id, ProductClassification.status == "confirmed")))
    q = select(Product).where(Product.organization_id == ctx.org_id)
    if body.product_ids is not None:
        q = q.where(Product.id.in_(body.product_ids))
    totals = {"alta": 0, "media": 0, "baixa": 0, "kept_confirmed": 0}
    current = {pc.product_id: pc for pc in ctx.db.scalars(select(ProductClassification).where(
        ProductClassification.organization_id == ctx.org_id))}
    for p in ctx.db.scalars(q.execution_options(yield_per=CHUNK)):
        if p.id in confirmed:
            totals["kept_confirmed"] += 1
            continue
        r = classify(p.name, p.description, p.attributes or {}, rules)
        totals[r.confidence] += 1
        pc = current.get(p.id) or ProductClassification(organization_id=ctx.org_id, product_id=p.id)
        pc.category_id = uuid.UUID(r.category_id) if r.category_id else None
        pc.status = "suggested" if r.category_id else "unclassified"
        pc.confidence, pc.score, pc.evidence = r.confidence, r.score, r.evidence + (
            [f"segunda opção: {r.runner_up}"] if r.runner_up and r.confidence != "alta" else [])
        pc.decided_by = None
        ctx.db.add(pc)
    audit.record(ctx.db, "classification.run", user_id=ctx.user.id, org_id=ctx.org_id, **totals)
    ctx.db.commit()
    return totals


@router.get("/classification")
def classification_list(ctx: OrgContext = Depends(require("catalog.read")),
                        view: Literal["review", "confirmed", "all"] = "review", limit: int = 200) -> list[dict]:
    paths = _paths(_cats(ctx))
    q = select(ProductClassification, Product).join(Product, Product.id == ProductClassification.product_id).where(
        ProductClassification.organization_id == ctx.org_id)
    if view == "review":
        q = q.where(ProductClassification.status != "confirmed")
    elif view == "confirmed":
        q = q.where(ProductClassification.status == "confirmed")
    order = {"media": 0, "baixa": 1, "alta": 2}
    rows = ctx.db.execute(q.limit(max(1, min(limit, 1000)))).all()
    out = [{"product_id": str(p.id), "sku": p.sku, "name": p.name, "status": pc.status, "confidence": pc.confidence,
            "score": pc.score, "evidence": pc.evidence,
            "category_id": str(pc.category_id) if pc.category_id else None,
            "category_path": paths.get(pc.category_id) if pc.category_id else None} for pc, p in rows]
    return sorted(out, key=lambda x: (order.get(x["confidence"], 3), x["name"]))


class ConfirmIn(BaseModel):
    product_ids: list[uuid.UUID] = Field(min_length=1, max_length=50_000)
    category_id: uuid.UUID | None = None   # None = accept each product's own suggestion
    mode: Literal["set", "accept_suggestion", "clear"] = "set"


@router.post("/classification/confirm")
def confirm(body: ConfirmIn, ctx: OrgContext = Depends(require("catalog.write"))) -> dict:
    if body.mode == "set":
        if body.category_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Escolha a categoria.")
        _category(ctx, body.category_id)
    valid = set(ctx.db.scalars(select(Product.id).where(Product.organization_id == ctx.org_id,
                                                        Product.id.in_(body.product_ids))))
    current = {pc.product_id: pc for pc in ctx.db.scalars(select(ProductClassification).where(
        ProductClassification.organization_id == ctx.org_id, ProductClassification.product_id.in_(valid)))}
    changed = 0
    for pid in valid:
        pc = current.get(pid) or ProductClassification(organization_id=ctx.org_id, product_id=pid, status="unclassified")
        if body.mode == "accept_suggestion":
            if pc.status != "suggested" or pc.category_id is None:
                continue
        elif body.mode == "set":
            pc.category_id = body.category_id
        else:  # clear: back to automatic
            pc.status, pc.decided_by = "unclassified", None
            ctx.db.add(pc)
            changed += 1
            continue
        pc.status, pc.decided_by = "confirmed", ctx.user.id
        pc.evidence = (pc.evidence or []) + ["confirmado manualmente"]
        ctx.db.add(pc)
        changed += 1
    audit.record(ctx.db, "classification.confirmed", user_id=ctx.user.id, org_id=ctx.org_id, mode=body.mode,
                 count=changed)
    ctx.db.commit()
    return {"changed": changed}
