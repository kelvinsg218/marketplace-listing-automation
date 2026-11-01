"""Variations, photos (Central de Fotos) and per-marketplace product data."""
from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import case, func, or_, select

from mla_api import audit
from mla_api.deps import OrgContext, require
from mla_api.domain.catalog import gtin_valid, normalize_gtin, sku_problem
from mla_api.domain.listing_rules import PHOTO_GROUP_LIMIT, photo_url_problem
from mla_api.models import Product, ProductChannelData, ProductImage, ProductVariant
from mla_api.routers.products import _get as get_product
from mla_api.schemas import UtcDatetime

router = APIRouter(prefix="/api/orgs/{org_id}", tags=["catalog-media"])

MAX_IMAGE_BYTES = 10 * 1024 * 1024
_IMAGE_MAGIC = ((b"\xff\xd8\xff", "image/jpeg"), (b"\x89PNG\r\n\x1a\n", "image/png"))


def sniff_image(data: bytes) -> str | None:
    for magic, ctype in _IMAGE_MAGIC:
        if data.startswith(magic):
            return ctype
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


# --- variants ---------------------------------------------------------------------------------------------------
class VariantIn(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    attributes: dict[str, str] = Field(min_length=1, max_length=10)
    gtin: str = Field(default="", max_length=32)
    price_cents: int | None = Field(default=None, ge=0, le=10**11)
    stock: int = Field(default=0, ge=0, le=10**9)

    @field_validator("sku")
    @classmethod
    def _sku(cls, v: str) -> str:
        if problem := sku_problem(v):
            raise ValueError(problem)
        return v.strip()

    @field_validator("attributes")
    @classmethod
    def _attrs(cls, v: dict[str, str]) -> dict[str, str]:
        clean = {k.strip()[:60]: str(val).strip()[:120] for k, val in v.items() if k.strip() and str(val).strip()}
        if not clean:
            raise ValueError("Informe ao menos um atributo da variação (ex.: Cor = Azul).")
        return clean

    @field_validator("gtin")
    @classmethod
    def _gtin(cls, v: str) -> str:
        digits = normalize_gtin(v)
        if v.strip() and len(digits) not in (8, 12, 13, 14):
            raise ValueError("GTIN/EAN precisa ter 8, 12, 13 ou 14 dígitos.")
        return digits


class VariantOut(BaseModel):
    id: uuid.UUID
    sku: str
    attributes: dict
    gtin: str
    gtin_valid: bool
    price_cents: int | None
    stock: int
    created_at: UtcDatetime


def _variant_out(v: ProductVariant) -> VariantOut:
    return VariantOut(id=v.id, sku=v.sku, attributes=v.attributes, gtin=v.gtin,
                      gtin_valid=not v.gtin or gtin_valid(v.gtin), price_cents=v.price_cents, stock=v.stock,
                      created_at=v.created_at)


def _sku_taken(ctx: OrgContext, sku: str, exclude_variant: uuid.UUID | None = None) -> bool:
    """SKUs are unique across products and variations of the organization."""
    if ctx.db.scalar(select(Product.id).where(Product.organization_id == ctx.org_id, Product.sku == sku)):
        return True
    q = select(ProductVariant.id).where(ProductVariant.organization_id == ctx.org_id, ProductVariant.sku == sku)
    if exclude_variant:
        q = q.where(ProductVariant.id != exclude_variant)
    return ctx.db.scalar(q) is not None


@router.get("/products/{product_id}/variants", response_model=list[VariantOut])
def list_variants(product_id: uuid.UUID, ctx: OrgContext = Depends(require("catalog.read"))) -> list[VariantOut]:
    get_product(ctx, product_id)
    rows = ctx.db.scalars(select(ProductVariant).where(ProductVariant.organization_id == ctx.org_id,
                                                       ProductVariant.product_id == product_id)
                          .order_by(ProductVariant.position, ProductVariant.created_at)).all()
    return [_variant_out(v) for v in rows]


@router.post("/products/{product_id}/variants", response_model=VariantOut, status_code=201)
def create_variant(product_id: uuid.UUID, body: VariantIn,
                   ctx: OrgContext = Depends(require("catalog.write"))) -> VariantOut:
    p = get_product(ctx, product_id)
    if _sku_taken(ctx, body.sku):
        raise HTTPException(status.HTTP_409_CONFLICT, f"O SKU {body.sku} já está em uso na organização.")
    position = ctx.db.scalar(select(func.count()).select_from(ProductVariant)
                             .where(ProductVariant.product_id == p.id)) or 0
    v = ProductVariant(organization_id=ctx.org_id, product_id=p.id, position=position, **body.model_dump())
    ctx.db.add(v)
    audit.record(ctx.db, "variant.created", user_id=ctx.user.id, org_id=ctx.org_id, target_type="product",
                 target_id=p.id, sku=body.sku)
    ctx.db.commit()
    return _variant_out(v)


def _get_variant(ctx: OrgContext, product_id: uuid.UUID, variant_id: uuid.UUID) -> ProductVariant:
    v = ctx.db.scalar(select(ProductVariant).where(ProductVariant.id == variant_id,
                                                   ProductVariant.product_id == product_id,
                                                   ProductVariant.organization_id == ctx.org_id))
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Variação não encontrada.")
    return v


@router.put("/products/{product_id}/variants/{variant_id}", response_model=VariantOut)
def update_variant(product_id: uuid.UUID, variant_id: uuid.UUID, body: VariantIn,
                   ctx: OrgContext = Depends(require("catalog.write"))) -> VariantOut:
    v = _get_variant(ctx, product_id, variant_id)
    if body.sku != v.sku and _sku_taken(ctx, body.sku, exclude_variant=v.id):
        raise HTTPException(status.HTTP_409_CONFLICT, f"O SKU {body.sku} já está em uso na organização.")
    for k, val in body.model_dump().items():
        setattr(v, k, val)
    audit.record(ctx.db, "variant.updated", user_id=ctx.user.id, org_id=ctx.org_id, target_type="product",
                 target_id=product_id, sku=v.sku)
    ctx.db.commit()
    return _variant_out(v)


@router.delete("/products/{product_id}/variants/{variant_id}", status_code=204, response_class=Response,
               response_model=None)
def delete_variant(product_id: uuid.UUID, variant_id: uuid.UUID,
                   ctx: OrgContext = Depends(require("catalog.write"))) -> None:
    v = _get_variant(ctx, product_id, variant_id)
    audit.record(ctx.db, "variant.deleted", user_id=ctx.user.id, org_id=ctx.org_id, target_type="product",
                 target_id=product_id, sku=v.sku)
    ctx.db.delete(v)
    ctx.db.commit()


# --- photos -----------------------------------------------------------------------------------------------------
class ImageOut(BaseModel):
    id: uuid.UUID
    position: int
    variant_id: uuid.UUID | None
    has_file: bool
    content_type: str
    size_bytes: int
    original_name: str
    official_url: str
    url_problem: str | None
    created_at: UtcDatetime


def _image_out(i: ProductImage) -> ImageOut:
    problem = photo_url_problem(i.official_url) if i.official_url else None
    return ImageOut(id=i.id, position=i.position, variant_id=i.variant_id, has_file=bool(i.storage_key),
                    content_type=i.content_type, size_bytes=i.size_bytes, original_name=i.original_name,
                    official_url=i.official_url, url_problem=problem.message if problem else None,
                    created_at=i.created_at)


def _images(ctx: OrgContext, product_id: uuid.UUID) -> list[ProductImage]:
    return list(ctx.db.scalars(select(ProductImage).where(ProductImage.organization_id == ctx.org_id,
                                                          ProductImage.product_id == product_id)
                               .order_by(ProductImage.position, ProductImage.created_at)))


def _get_image(ctx: OrgContext, product_id: uuid.UUID, image_id: uuid.UUID) -> ProductImage:
    i = ctx.db.scalar(select(ProductImage).where(ProductImage.id == image_id, ProductImage.product_id == product_id,
                                                 ProductImage.organization_id == ctx.org_id))
    if i is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foto não encontrada.")
    return i


def _check_url(url: str) -> str:
    url = url.strip()
    if url and (problem := photo_url_problem(url)) and problem.severity == "error":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem.message)
    return url


@router.get("/products/{product_id}/images", response_model=list[ImageOut])
def list_images(product_id: uuid.UUID, ctx: OrgContext = Depends(require("catalog.read"))) -> list[ImageOut]:
    get_product(ctx, product_id)
    return [_image_out(i) for i in _images(ctx, product_id)]


@router.post("/products/{product_id}/images/upload", response_model=ImageOut, status_code=201)
async def upload_image(product_id: uuid.UUID, file: UploadFile = File(...),
                       ctx: OrgContext = Depends(require("catalog.write"))) -> ImageOut:
    p = get_product(ctx, product_id)
    data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Imagem maior que 10 MB.")
    ctype = sniff_image(data)
    if ctype is None:  # the declared type and extension are ignored: only the bytes count
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Envie uma imagem JPG, PNG ou WEBP.")
    image_id = uuid.uuid4()
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[ctype]
    key = ctx.storage.put(ctx.org_id, "media", f"{image_id}.{ext}", data)
    position = len(_images(ctx, p.id))
    i = ProductImage(id=image_id, organization_id=ctx.org_id, product_id=p.id, position=position, storage_key=key,
                     content_type=ctype, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                     original_name=(file.filename or "")[:255], official_url="")
    ctx.db.add(i)
    audit.record(ctx.db, "image.uploaded", user_id=ctx.user.id, org_id=ctx.org_id, target_type="product",
                 target_id=p.id, sku=p.sku)
    ctx.db.commit()
    return _image_out(i)


class ImageUrlIn(BaseModel):
    official_url: str = Field(min_length=1, max_length=500)


@router.post("/products/{product_id}/images", response_model=list[ImageOut], status_code=201)
def add_official_urls(product_id: uuid.UUID, body: list[ImageUrlIn],
                      ctx: OrgContext = Depends(require("catalog.write"))) -> list[ImageOut]:
    """Registers URLs copied from the Gestor de fotos (P3 p.3). Accepts the comma-separated text copied from it."""
    p = get_product(ctx, product_id)
    urls = [u.strip() for item in body for u in item.official_url.split(",") if u.strip()]
    if not urls or len(urls) > 50:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Informe entre 1 e 50 URLs.")
    urls = [_check_url(u) for u in urls]
    position = len(_images(ctx, p.id))
    for n, url in enumerate(urls):
        ctx.db.add(ProductImage(organization_id=ctx.org_id, product_id=p.id, position=position + n,
                                official_url=url))
    audit.record(ctx.db, "image.urls_added", user_id=ctx.user.id, org_id=ctx.org_id, target_type="product",
                 target_id=p.id, sku=p.sku, count=len(urls))
    ctx.db.commit()
    return [_image_out(i) for i in _images(ctx, p.id)]


class ImagePatch(BaseModel):
    official_url: str | None = Field(default=None, max_length=500)
    variant_id: uuid.UUID | None = None
    clear_variant: bool = False


@router.patch("/products/{product_id}/images/{image_id}", response_model=ImageOut)
def update_image(product_id: uuid.UUID, image_id: uuid.UUID, body: ImagePatch,
                 ctx: OrgContext = Depends(require("catalog.write"))) -> ImageOut:
    i = _get_image(ctx, product_id, image_id)
    if body.official_url is not None:
        i.official_url = _check_url(body.official_url)
    if body.variant_id is not None:
        _get_variant(ctx, product_id, body.variant_id)
        i.variant_id = body.variant_id
    elif body.clear_variant:
        i.variant_id = None
    ctx.db.commit()
    return _image_out(i)


class ReorderIn(BaseModel):
    ids: list[uuid.UUID]


@router.put("/products/{product_id}/images/order", response_model=list[ImageOut])
def reorder_images(product_id: uuid.UUID, body: ReorderIn,
                   ctx: OrgContext = Depends(require("catalog.write"))) -> list[ImageOut]:
    images = _images(ctx, product_id)
    if sorted(map(str, body.ids)) != sorted(str(i.id) for i in images):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A nova ordem precisa conter todas as fotos.")
    by_id = {i.id: i for i in images}
    for n, image_id in enumerate(body.ids):
        by_id[image_id].position = n
    ctx.db.commit()
    return [_image_out(i) for i in _images(ctx, product_id)]


@router.delete("/products/{product_id}/images/{image_id}", status_code=204, response_class=Response,
               response_model=None)
def delete_image(product_id: uuid.UUID, image_id: uuid.UUID,
                 ctx: OrgContext = Depends(require("catalog.write"))) -> None:
    i = _get_image(ctx, product_id, image_id)
    key = i.storage_key
    ctx.db.delete(i)
    audit.record(ctx.db, "image.deleted", user_id=ctx.user.id, org_id=ctx.org_id, target_type="product",
                 target_id=product_id)
    ctx.db.commit()
    if key:
        ctx.storage.delete(ctx.org_id, key)


@router.get("/products/{product_id}/images/{image_id}/file")
def image_file(product_id: uuid.UUID, image_id: uuid.UUID,
               ctx: OrgContext = Depends(require("catalog.read"))) -> Response:
    """Authorized download: files are never in a public folder."""
    i = _get_image(ctx, product_id, image_id)
    if not i.storage_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esta foto só tem URL oficial, sem arquivo.")
    try:
        data = ctx.storage.read(ctx.org_id, i.storage_key)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Arquivo da foto não encontrado no armazenamento.")
    return Response(data, media_type=i.content_type,
                    headers={"Cache-Control": "private, max-age=300", "Content-Disposition": "inline"})


# --- Central de Fotos overview ----------------------------------------------------------------------------------
class PhotoStatusOut(BaseModel):
    product_id: uuid.UUID
    sku: str
    name: str
    images: int
    with_url: int
    without_url: int
    over_group_limit: bool


@router.get("/photos/status", response_model=list[PhotoStatusOut])
def photo_status(ctx: OrgContext = Depends(require("catalog.read")), q: str = "", only_pending: bool = False,
                 limit: int = 100, offset: int = 0) -> list[PhotoStatusOut]:
    with_url = func.sum(case((func.length(ProductImage.official_url) > 0, 1), else_=0))
    stmt = (select(Product.id, Product.sku, Product.name, func.count(ProductImage.id), func.coalesce(with_url, 0))
            .outerjoin(ProductImage, (ProductImage.product_id == Product.id)
                       & (ProductImage.organization_id == ctx.org_id))
            .where(Product.organization_id == ctx.org_id).group_by(Product.id, Product.sku, Product.name)
            .order_by(Product.name))
    if q.strip():
        like = f"%{q.strip().replace('%', '').replace('_', '')}%"
        stmt = stmt.where(or_(Product.name.ilike(like), Product.sku.ilike(like)))
    rows = ctx.db.execute(stmt.limit(max(1, min(limit, 500))).offset(max(0, offset))).all()
    out = [PhotoStatusOut(product_id=pid, sku=sku, name=name, images=total, with_url=int(urls),
                          without_url=total - int(urls), over_group_limit=int(urls) > PHOTO_GROUP_LIMIT)
           for pid, sku, name, total, urls in rows]
    if only_pending:
        out = [o for o in out if o.with_url == 0 or o.without_url]
    return out


# --- per-marketplace data ---------------------------------------------------------------------------------------
class ChannelIn(BaseModel):
    catalog_code: str = Field(default="", max_length=40, pattern=r"^[A-Za-z0-9-]*$")
    category_id: str = Field(default="", max_length=40, pattern=r"^[A-Za-z0-9-]*$")


class ChannelOut(ChannelIn):
    marketplace: str


@router.get("/products/{product_id}/channels/{marketplace}", response_model=ChannelOut)
def get_channel(product_id: uuid.UUID, marketplace: str,
                ctx: OrgContext = Depends(require("catalog.read"))) -> ChannelOut:
    get_product(ctx, product_id)
    row = ctx.db.scalar(select(ProductChannelData).where(ProductChannelData.product_id == product_id,
                                                         ProductChannelData.organization_id == ctx.org_id,
                                                         ProductChannelData.marketplace == marketplace))
    return ChannelOut(marketplace=marketplace, catalog_code=row.catalog_code if row else "",
                      category_id=row.category_id if row else "")


@router.put("/products/{product_id}/channels/{marketplace}", response_model=ChannelOut)
def put_channel(product_id: uuid.UUID, marketplace: str, body: ChannelIn,
                ctx: OrgContext = Depends(require("catalog.write"))) -> ChannelOut:
    if marketplace != "mercadolivre":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Marketplace não suportado.")
    get_product(ctx, product_id)
    row = ctx.db.scalar(select(ProductChannelData).where(ProductChannelData.product_id == product_id,
                                                         ProductChannelData.organization_id == ctx.org_id,
                                                         ProductChannelData.marketplace == marketplace))
    if row is None:
        row = ProductChannelData(organization_id=ctx.org_id, product_id=product_id, marketplace=marketplace)
        ctx.db.add(row)
    row.catalog_code, row.category_id = body.catalog_code, body.category_id
    ctx.db.commit()
    return ChannelOut(marketplace=marketplace, catalog_code=row.catalog_code, category_id=row.category_id)
