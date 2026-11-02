"""Loads catalog rows into the plain structures the listing rules work on (always scoped to one organization)."""
from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from mla_api.domain.listing_rules import ProductData, VariantData
from mla_api.models import Product, ProductChannelData, ProductImage, ProductVariant

_CHUNK = 500


def load_products(db: Session, org_id: uuid.UUID, product_ids: list[uuid.UUID],
                  marketplace: str = "mercadolivre") -> list[ProductData]:
    out: list[ProductData] = []
    for start in range(0, len(product_ids), _CHUNK):
        ids = product_ids[start:start + _CHUNK]
        products = db.scalars(select(Product).where(Product.organization_id == org_id, Product.id.in_(ids))
                              .order_by(Product.name)).all()
        variants, urls, without_url, codes = defaultdict(list), defaultdict(list), defaultdict(int), {}
        for v in db.scalars(select(ProductVariant).where(ProductVariant.organization_id == org_id,
                                                         ProductVariant.product_id.in_(ids))
                            .order_by(ProductVariant.position, ProductVariant.created_at)):
            variants[v.product_id].append(VariantData(v.sku, dict(v.attributes), v.gtin, v.price_cents, v.stock))
        # Only approved images reach a sheet (AI versions stay pending until a person approves them).
        for i in db.scalars(select(ProductImage).where(ProductImage.organization_id == org_id,
                                                       ProductImage.product_id.in_(ids),
                                                       ProductImage.status == "approved")
                            .order_by(ProductImage.position, ProductImage.created_at)):
            if i.official_url:
                urls[i.product_id].append(i.official_url)
            else:
                without_url[i.product_id] += 1
        for c in db.scalars(select(ProductChannelData).where(ProductChannelData.organization_id == org_id,
                                                             ProductChannelData.product_id.in_(ids),
                                                             ProductChannelData.marketplace == marketplace)):
            codes[c.product_id] = c.catalog_code
        for p in products:
            out.append(ProductData(
                id=str(p.id), sku=p.sku, name=p.name, brand=p.brand, model=p.model, gtin=p.gtin,
                description=p.description, price_cents=p.price_cents, stock=p.stock,
                attributes={str(k): str(v) for k, v in (p.attributes or {}).items()},
                variants=variants[p.id], photo_urls=urls[p.id], photos_without_url=without_url[p.id],
                catalog_code=codes.get(p.id, "")))
    return out
