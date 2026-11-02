"""Central de Imagens and Estúdio de IA (see services/image_ai.py and services/safe_fetch.py)."""
from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select

from mla_api import audit
from mla_api.services import ai_budget
from mla_api.db import utcnow
from mla_api.deps import OrgContext, require
from mla_api.models import Product, ProductImage
from mla_api.routers.media import ImageOut, _get_image, _image_out, _images, sniff_image
from mla_api.routers.products import _get as get_product, category_condition
from mla_api.services.image_ai import PRESERVE_PRODUCT, ImageEditError
from mla_api.services.safe_fetch import FetchRefused, fetch_image

router = APIRouter(prefix="/api/orgs/{org_id}", tags=["images"])
EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def _store(ctx: OrgContext, p: Product, data: bytes, ctype: str, **fields) -> ProductImage:
    image_id = uuid.uuid4()
    key = ctx.storage.put(ctx.org_id, "media", f"{image_id}.{EXT[ctype]}", data)
    img = ProductImage(id=image_id, organization_id=ctx.org_id, product_id=p.id, position=len(_images(ctx, p.id)),
                       storage_key=key, content_type=ctype, size_bytes=len(data),
                       sha256=hashlib.sha256(data).hexdigest(), **fields)
    ctx.db.add(img)
    return img


@router.get("/images/products")
def image_overview(ctx: OrgContext = Depends(require("catalog.read")), q: str = "", category_id: uuid.UUID | None = None,
                   only_pending: bool = False, limit: int = 100, offset: int = 0) -> dict:
    """Products with image counts (search by name, SKU or GTIN; category filter)."""
    approved = func.sum(case((ProductImage.status == "approved", 1), else_=0))
    pending = func.sum(case((ProductImage.status == "pending", 1), else_=0))
    gestor = func.sum(case(((ProductImage.status == "approved") & (func.length(ProductImage.official_url) > 0), 1),
                           else_=0))
    cond = [Product.organization_id == ctx.org_id]
    if q.strip():
        like = f"%{q.strip().replace('%', '').replace('_', '')}%"
        cond.append(or_(Product.name.ilike(like), Product.sku.ilike(like), Product.gtin.like(like)))
    if category_id:
        cond.append(category_condition(ctx, category_id))
    stmt = (select(Product.id, Product.sku, Product.name, Product.gtin, func.count(ProductImage.id),
                   func.coalesce(approved, 0), func.coalesce(pending, 0), func.coalesce(gestor, 0))
            .outerjoin(ProductImage, (ProductImage.product_id == Product.id)
                       & (ProductImage.organization_id == ctx.org_id))
            .where(*cond).group_by(Product.id, Product.sku, Product.name, Product.gtin).order_by(Product.name))
    rows = ctx.db.execute(stmt.limit(max(1, min(limit, 500))).offset(max(0, offset))).all()
    items = [{"product_id": str(pid), "sku": sku, "name": name, "gtin": gtin, "images": int(total),
              "approved": int(ok), "pending": int(pend), "with_gestor_url": int(gurl)}
             for pid, sku, name, gtin, total, ok, pend, gurl in rows]
    if only_pending:
        items = [i for i in items if i["pending"] or i["approved"] == 0 or i["with_gestor_url"] == 0]
    return {"items": items}


class UrlIn(BaseModel):
    url: str = Field(min_length=8, max_length=500)


@router.post("/products/{product_id}/images/from-url", response_model=ImageOut, status_code=201)
def import_from_url(product_id: uuid.UUID, body: UrlIn, request: Request,
                    ctx: OrgContext = Depends(require("catalog.write"))) -> ImageOut:
    """Downloads the image (SSRF-safe) and stores it as a file of the organization; the URL is kept as reference."""
    p = get_product(ctx, product_id)
    fetcher = getattr(request.app.state, "image_fetcher", None) or fetch_image
    try:
        data, ctype = fetcher(body.url, sniff_image)
    except FetchRefused as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    img = _store(ctx, p, data, ctype, source="url_externa", external_url=body.url.strip()[:500],
                 original_name=body.url.rsplit("/", 1)[-1][:255], official_url="", status="approved")
    audit.record(ctx.db, "image.imported_url", user_id=ctx.user.id, org_id=ctx.org_id, target_type="product",
                 target_id=p.id, sku=p.sku)
    ctx.db.commit()
    return _image_out(img)


def _make_primary(ctx: OrgContext, product_id: uuid.UUID, image: ProductImage) -> None:
    order = [image] + [i for i in _images(ctx, product_id) if i.id != image.id]
    for n, i in enumerate(order):
        i.position = n


@router.post("/products/{product_id}/images/{image_id}/primary", response_model=list[ImageOut])
def set_primary(product_id: uuid.UUID, image_id: uuid.UUID,
                ctx: OrgContext = Depends(require("catalog.write"))) -> list[ImageOut]:
    img = _get_image(ctx, product_id, image_id)
    if img.status != "approved":
        raise HTTPException(status.HTTP_409_CONFLICT, "Aprove a imagem antes de torná-la principal.")
    _make_primary(ctx, product_id, img)
    ctx.db.commit()
    return [_image_out(i) for i in _images(ctx, product_id)]


class ReviewIn(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    set_primary: bool = False


@router.post("/products/{product_id}/images/{image_id}/review", response_model=ImageOut)
def review(product_id: uuid.UUID, image_id: uuid.UUID, body: ReviewIn,
           ctx: OrgContext = Depends(require("catalog.write"))) -> ImageOut:
    img = _get_image(ctx, product_id, image_id)
    img.status = "approved" if body.decision == "approve" else "rejected"
    img.reviewed_by, img.reviewed_at = ctx.user.id, utcnow()
    if body.decision == "approve" and body.set_primary:
        _make_primary(ctx, product_id, img)
    audit.record(ctx.db, f"image.{img.status}", user_id=ctx.user.id, org_id=ctx.org_id, target_type="product",
                 target_id=product_id, image=str(img.id), source=img.source)
    ctx.db.commit()
    return _image_out(img)


def _budget(request: Request, ctx: OrgContext) -> dict | None:
    st = request.app.state.settings
    if (st.image_ai_provider or "").strip().lower() != "openai":
        return None
    return {**ai_budget.snapshot(ctx.db, "openai", st.image_ai_budget_usd), "reserve_usd": st.image_ai_reserve_usd}


@router.get("/images/ai/status")
def ai_status(request: Request, ctx: OrgContext = Depends(require("catalog.read"))) -> dict:
    """What the studio can do right now. Never returns the key (only whether one is configured)."""
    p, st = request.app.state.image_ai, request.app.state.settings
    budget = _budget(request, ctx)
    blocked = bool(budget and budget["remaining_usd"] < st.image_ai_reserve_usd)
    return {"configured": p is not None, "provider": getattr(p, "name", None), "external": getattr(p, "external", None),
            "paid": getattr(p, "paid", False), "model": getattr(p, "model", None),
            "quality": getattr(p, "quality", None), "budget": budget, "blocked": blocked,
            "preserve_product": PRESERVE_PRODUCT.rsplit(" User request:", 1)[0],
            "message": request.app.state.image_ai_message if p is None else
            (f"Limite interno de US$ {st.image_ai_budget_usd:.2f} atingido; novas edições estão bloqueadas."
             if blocked else None)}


class EditIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=1000)
    consent: bool = False


def _root_original(ctx: OrgContext, product_id: uuid.UUID, img: ProductImage) -> ProductImage:
    """AI versions are always made from the original photo, never from another AI result."""
    seen = set()
    while img.source == "ia" and img.parent_image_id and img.parent_image_id not in seen:
        seen.add(img.id)
        img = _get_image(ctx, product_id, img.parent_image_id)
    return img


@router.post("/products/{product_id}/images/{image_id}/ai-edit", response_model=ImageOut, status_code=201)
def ai_edit(product_id: uuid.UUID, image_id: uuid.UUID, body: EditIn, request: Request,
            ctx: OrgContext = Depends(require("catalog.write"))) -> ImageOut:
    """One image per request (no bulk editing). The result is a NEW pending version (a preview until a person
    approves it); the original is never changed. Paid providers run under the installation budget (D-035)."""
    provider, st = request.app.state.image_ai, request.app.state.settings
    if provider is None:
        raise HTTPException(status.HTTP_409_CONFLICT, request.app.state.image_ai_message
                            or "Edição por IA não configurada nesta instalação.")
    if provider.external and not body.consent:
        raise HTTPException(status.HTTP_409_CONFLICT, "Confirme que autoriza enviar esta imagem ao provedor externo.")
    if len(body.prompt) > provider.max_prompt:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Instrução acima de {provider.max_prompt} caracteres.")
    p = get_product(ctx, product_id)
    src = _root_original(ctx, product_id, _get_image(ctx, product_id, image_id))
    if not src.storage_key:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta imagem só tem URL; importe o arquivo antes de editar.")
    original = ctx.storage.read(ctx.org_id, src.storage_key)
    src_id, src_name, src_ctype, sku = src.id, src.original_name, src.content_type, p.sku
    paid = getattr(provider, "paid", False)
    reserve = st.image_ai_reserve_usd
    if paid and not ai_budget.reserve(ctx.db, provider.name, st.image_ai_budget_usd, reserve):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Limite interno de US$ {st.image_ai_budget_usd:.2f} atingido; "
                                                      "novas edições estão bloqueadas.")
    safety_id = hashlib.sha256(f"mla:{ctx.org_id}:{ctx.user.id}".encode()).hexdigest()
    try:
        result = provider.edit(original, src_ctype, body.prompt, safety_id=safety_id)
    except ImageEditError as exc:
        charged = ai_budget.settle(ctx.db, provider.name, reserve, exc.charged_usd) if paid else 0
        audit.record(ctx.db, "image.ai_failed", user_id=ctx.user.id, org_id=ctx.org_id, target_type="product",
                     target_id=product_id, provider=provider.name, cost_micro_usd=charged, error=str(exc)[:300])
        ctx.db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"O provedor recusou a edição: {exc}")
    charged = ai_budget.settle(ctx.db, provider.name, reserve, result.cost_usd) if paid else 0
    ctype = sniff_image(result.data)
    if ctype is None:
        audit.record(ctx.db, "image.ai_failed", user_id=ctx.user.id, org_id=ctx.org_id, target_type="product",
                     target_id=product_id, provider=provider.name, cost_micro_usd=charged, error="invalid image")
        ctx.db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "O provedor não devolveu uma imagem válida.")
    p = get_product(ctx, product_id)
    img = _store(ctx, p, result.data, ctype, source="ia", parent_image_id=src_id, prompt=body.prompt,
                 provider=provider.name, status="pending", original_name=f"IA de {src_name or 'imagem'}"[:255],
                 official_url="", cost_micro_usd=charged,
                 ai_usage={"model": result.model, **({"usage": result.usage} if result.usage else {}),
                           "cost_reported": result.cost_usd is not None})
    audit.record(ctx.db, "image.ai_edited", user_id=ctx.user.id, org_id=ctx.org_id, target_type="product",
                 target_id=p.id, sku=sku, provider=provider.name, model=result.model, external=provider.external,
                 consent=body.consent, cost_micro_usd=charged)
    ctx.db.commit()
    return _image_out(img)
