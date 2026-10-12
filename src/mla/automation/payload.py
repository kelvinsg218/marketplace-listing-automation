from __future__ import annotations

from mla.automation.base import ListingPayload
from mla.core.enums import Marketplace
from mla.core.models import Product
from mla.services.images import ImageStore


def compose_description(product: Product) -> str:
    """Description as sent to the marketplace: free text plus structured sections."""
    parts = [product.description.strip()]
    features = [line.strip(" -•\t") for line in product.features.splitlines() if line.strip()]
    if features:
        parts.append("Características:\n" + "\n".join(f"- {f}" for f in features))
    if product.material.strip():
        parts.append(f"Material: {product.material.strip()}")
    if product.package_contents.strip():
        parts.append(f"Conteúdo da embalagem: {product.package_contents.strip()}")
    if product.warranty.strip():
        parts.append(f"Garantia: {product.warranty.strip()}")
    return "\n\n".join(p for p in parts if p)


def build_payload(product: Product, marketplace: Marketplace, images: ImageStore) -> ListingPayload:
    data = product.marketplace_data.get(marketplace)
    ordered = sorted(product.images, key=lambda i: (not i.is_main, i.position))
    attributes = dict(data.attributes) if data else {}
    if product.brand and "Marca" not in attributes:
        attributes["Marca"] = product.brand
    if product.model and "Modelo" not in attributes:
        attributes["Modelo"] = product.model
    stock = sum(v.stock for v in product.variants) if product.variants else product.stock
    return ListingPayload(
        product_id=product.id or 0,
        sku=product.sku,
        title=product.title.strip(),
        category=product.category,
        category_id=data.category_id if data else "",
        listing_type=data.listing_type if data else "",
        condition=product.condition.value,
        description=compose_description(product),
        price_cents=product.price_for(marketplace) or 0,
        stock=stock,
        weight_g=product.weight_g or 0,
        length_mm=product.length_mm or 0,
        width_mm=product.width_mm or 0,
        height_mm=product.height_mm or 0,
        images=[images.path_for(i.filename) for i in ordered],
        attributes=attributes,
        brand=product.brand,
        model=product.model,
    )
