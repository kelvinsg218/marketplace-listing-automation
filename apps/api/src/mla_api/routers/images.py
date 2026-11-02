"""Central de Imagens and Estúdio de IA (see services/image_ai.py and services/safe_fetch.py)."""
from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select

from mla_api import audit
from mla_api.db import utcnow
from mla_api.deps import OrgContext, require
from mla_api.models import Product, ProductImage
from mla_api.routers.media import ImageOut, _get_image, _image_out, _images, sniff_image
from mla_api.routers.products import _get as get_product, category_condition
from mla_api.services.image_ai import ImageEditError
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


@router.get("/images/ai/status")
def ai_status(request: Request, ctx: OrgContext = Depends(require("catalog.read"))) -> dict:
    p = request.app.state.image_ai
    return {"configured": p is not None, "provider": getattr(p, "name", None), "external": getattr(p, "external", None),
            "message": None if p else "A edição por IA depende da configuração de um provedor (MLA_IMAGE_AI_PROVIDER). "
                                      "Nenhum provedor está configurado; nada é simulado."}


class EditIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=1000)
    consent: bool = False


@router.post("/products/{product_id}/images/{image_id}/ai-edit", response_model=ImageOut, status_code=201)
def ai_edit(product_id: uuid.UUID, image_id: uuid.UUID, body: EditIn, request: Request,
            ctx: OrgContext = Depends(require("catalog.write"))) -> ImageOut:
    """Creates a NEW pending version from the provider's result; the original is never changed."""
    provider = request.app.state.image_ai
    if provider is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Edição por IA não configurada nesta instalação.")
    if provider.external and not body.consent:
        raise HTTPException(status.HTTP_409_CONFLICT, "Confirme que autoriza enviar esta imagem ao provedor externo.")
    p = get_product(ctx, product_id)
    src = _get_image(ctx, product_id, image_id)
    if not src.storage_key:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta imagem só tem URL; importe o arquivo antes de editar.")
    original = ctx.storage.read(ctx.org_id, src.storage_key)
    try:
        result = provider.edit(original, src.content_type, body.prompt)
    except ImageEditError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"O provedor recusou a edição: {exc}")
    ctype = sniff_image(result)
    if ctype is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "O provedor não devolveu uma imagem válida.")
    img = _store(ctx, p, result, ctype, source="ia", parent_image_id=src.id, prompt=body.prompt,
                 provider=provider.name, status="pending", original_name=f"IA de {src.original_name or 'imagem'}"[:255],
                 official_url="")
    audit.record(ctx.db, "image.ai_edited", user_id=ctx.user.id, org_id=ctx.org_id, target_type="product",
                 target_id=p.id, provider=provider.name, external=provider.external, consent=body.consent)
    ctx.db.commit()
    return _image_out(img)
