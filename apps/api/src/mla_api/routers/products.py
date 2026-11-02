from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from mla_api import audit
from mla_api.deps import OrgContext, require
from mla_api.domain.catalog import catalog_pendings, is_complete
from mla_api.models import Category, ListingBatch, Product, ProductClassification, ProductStatus
from mla_api.routers.orgs import recent_audit
from mla_api.schemas import DashboardOut, PendingOut, ProductIn, ProductOut, ProductPage, ProductPatch

router = APIRouter(prefix="/api/orgs/{org_id}", tags=["catalog"])

_SORTS = {"updated": Product.updated_at.desc(), "name": Product.name.asc(), "sku": Product.sku.asc()}


def pendings_of(p: Product):
    return catalog_pendings(name=p.name, brand=p.brand, gtin=p.gtin, description=p.description,
                            price_cents=p.price_cents)


def _out(p: Product) -> ProductOut:
    return ProductOut.model_validate(p).model_copy(
        update={"pendings": [PendingOut(**vars(x)) for x in pendings_of(p)]})


def _get(ctx: OrgContext, product_id: uuid.UUID) -> Product:
    # Always filtered by organization: an id from another organization answers 404.
    p = ctx.db.scalar(select(Product).where(Product.id == product_id, Product.organization_id == ctx.org_id))
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Produto não encontrado.")
    return p


def category_condition(ctx: OrgContext, category_id: uuid.UUID):
    """Products whose CONFIRMED classification is the category or one of its sub-categories."""
    ids = {category_id}
    frontier = {category_id}
    while frontier:  # categories are a shallow tree; this also stops on accidental cycles
        children = set(ctx.db.scalars(select(Category.id).where(Category.organization_id == ctx.org_id,
                                                                Category.parent_id.in_(frontier)))) - ids
        ids |= children
        frontier = children
    return Product.id.in_(select(ProductClassification.product_id).where(
        ProductClassification.organization_id == ctx.org_id, ProductClassification.status == "confirmed",
        ProductClassification.category_id.in_(ids)))


@router.get("/products", response_model=ProductPage)
def list_products(ctx: OrgContext = Depends(require("catalog.read")),
                  q: str = Query("", max_length=100), status_: ProductStatus | None = Query(None, alias="status"),
                  sort: Literal["updated", "name", "sku"] = "updated", category_id: uuid.UUID | None = None,
                  limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)) -> ProductPage:
    cond = [Product.organization_id == ctx.org_id]
    if q.strip():
        like = f"%{q.strip().replace('%', '').replace('_', '')}%"
        cond.append(or_(Product.name.ilike(like), Product.sku.ilike(like), Product.brand.ilike(like),
                        Product.gtin.like(like)))
    if status_:
        cond.append(Product.status == status_)
    if category_id:
        cond.append(category_condition(ctx, category_id))
    total = ctx.db.scalar(select(func.count()).select_from(Product).where(*cond))
    rows = ctx.db.scalars(select(Product).where(*cond).order_by(_SORTS[sort], Product.id)
                          .limit(limit).offset(offset)).all()
    return ProductPage(items=[_out(p) for p in rows], total=total, limit=limit, offset=offset)


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(body: ProductIn, ctx: OrgContext = Depends(require("catalog.write"))) -> ProductOut:
    p = Product(organization_id=ctx.org_id, **body.model_dump())
    ctx.db.add(p)
    try:
        ctx.db.flush()
    except IntegrityError:
        ctx.db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Já existe um produto com o SKU {body.sku}.")
    audit.record(ctx.db, "product.created", user_id=ctx.user.id, org_id=ctx.org_id, target_type="product",
                 target_id=p.id, sku=p.sku)
    ctx.db.commit()
    return _out(p)


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: uuid.UUID, ctx: OrgContext = Depends(require("catalog.read"))) -> ProductOut:
    return _out(_get(ctx, product_id))


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: uuid.UUID, body: ProductPatch,
                   ctx: OrgContext = Depends(require("catalog.write"))) -> ProductOut:
    p = _get(ctx, product_id)
    changed = {}
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None and field not in ("price_cents", "cost_cents"):
            continue
        if getattr(p, field) != value:
            changed[field] = value
            setattr(p, field, value)
    if changed:
        audit.record(ctx.db, "product.updated", user_id=ctx.user.id, org_id=ctx.org_id, target_type="product",
                     target_id=p.id, sku=p.sku, fields=sorted(changed))
        ctx.db.commit()
    return _out(p)


@router.delete("/products/{product_id}", status_code=204, response_class=Response, response_model=None)
def delete_product(product_id: uuid.UUID, ctx: OrgContext = Depends(require("catalog.write"))) -> None:
    p = _get(ctx, product_id)
    audit.record(ctx.db, "product.deleted", user_id=ctx.user.id, org_id=ctx.org_id, target_type="product",
                 target_id=p.id, sku=p.sku)
    ctx.db.delete(p)
    ctx.db.commit()


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(ctx: OrgContext = Depends(require("catalog.read"))) -> DashboardOut:
    by_status = dict(ctx.db.execute(
        select(Product.status, func.count()).where(Product.organization_id == ctx.org_id)
        .group_by(Product.status)).all())
    total = sum(by_status.values())
    # Completeness needs the Python rule (GTIN check digit); columns only, streamed in chunks.
    complete = 0
    stmt = (select(Product.name, Product.brand, Product.gtin, Product.description, Product.price_cents)
            .where(Product.organization_id == ctx.org_id).execution_options(yield_per=1000))
    for name, brand, gtin, description, price in ctx.db.execute(stmt):
        if is_complete(catalog_pendings(name=name, brand=brand, gtin=gtin, description=description,
                                        price_cents=price)):
            complete += 1
    batches = ctx.db.scalar(select(func.count()).select_from(ListingBatch)
                            .where(ListingBatch.organization_id == ctx.org_id))
    return DashboardOut(products_total=total, products_complete=complete, products_with_pendings=total - complete,
                        batches_total=batches,
                        products_by_status={s.value: by_status.get(s.value, 0) for s in ProductStatus},
                        recent_activity=recent_audit(ctx, 8))
