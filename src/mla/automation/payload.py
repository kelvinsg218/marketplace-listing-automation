from __future__ import annotations

from mla.automation.base import ListingPayload
from mla.core.enums import Marketplace
from mla.core.models import Listing, Product, ProductImage
from mla.services.images import ImageStore


def compose_description(product: Product) -> str:
    """Description as sent to the marketplace: free text plus structured sections (client data only)."""
    parts = [product.description.strip()]
    features = [line.strip(" -•\t") for line in product.features.splitlines() if line.strip()]
    if features:
        parts.append("Características:\n" + "\n".join(f"- {f}" for f in features))
    if product.technical_description.strip():
        parts.append("Ficha técnica:\n" + product.technical_description.strip())
    specs = [(k.strip(), v.strip()) for k, v in product.specs.items() if k.strip() and v.strip()]
    if specs:
        parts.append("Especificações:\n" + "\n".join(f"- {k}: {v}" for k, v in specs))
    if product.material.strip():
        parts.append(f"Material: {product.material.strip()}")
    if product.color.strip():
        parts.append(f"Cor: {product.color.strip()}")
    if product.package_contents.strip():
        parts.append(f"Conteúdo da embalagem: {product.package_contents.strip()}")
    if product.warranty.strip():
        parts.append(f"Garantia: {product.warranty.strip()}")
    return "\n\n".join(p for p in parts if p)


def listing_images(product: Product, listing: Listing | None = None) -> list[ProductImage]:
    """Images the offer uses: the listing's selection (in its order) or all product images, main first."""
    if listing is not None and listing.image_files:
        by_name = {i.filename: i for i in product.images}
        chosen = [by_name[f] for f in listing.image_files if f in by_name]
        if chosen:
            return chosen
    return sorted(product.images, key=lambda i: (not i.is_main, i.position))


def build_payload(product: Product, marketplace: Marketplace, images: ImageStore,
                  listing: Listing | None = None) -> ListingPayload:
    """Master product + per-marketplace data + the listing's overrides (empty override = master value)."""
    data = product.marketplace_data.get(marketplace)
    attributes = dict(data.attributes) if data else {}
    if product.brand and "Marca" not in attributes:
        attributes["Marca"] = product.brand
    if product.model and "Modelo" not in attributes:
        attributes["Modelo"] = product.model
    stock = sum(v.stock for v in product.variants) if product.variants else product.stock
    price = product.price_for(marketplace) or 0
    title = product.title.strip()
    description = compose_description(product)
    category_id = data.category_id if data else ""
    listing_type = data.listing_type if data else ""
    if listing is not None:
        title = listing.title.strip() or title
        description = listing.description.strip() or description
        price = listing.price_cents if listing.price_cents is not None else price
        stock = listing.stock if listing.stock is not None else stock
        category_id = listing.category_id.strip() or category_id
        listing_type = listing.listing_type.strip() or listing_type
        attributes.update({k: v for k, v in listing.attributes.items() if k.strip() and v.strip()})
    return ListingPayload(
        product_id=product.id or 0,
        sku=product.sku,
        title=title,
        category=product.category,
        category_id=category_id,
        listing_type=listing_type,
        condition=product.condition.value,
        description=description,
        price_cents=price,
        stock=stock,
        weight_g=product.weight_g or 0,
        length_mm=product.length_mm or 0,
        width_mm=product.width_mm or 0,
        height_mm=product.height_mm or 0,
        images=[images.path_for(i.filename) for i in listing_images(product, listing)],
        attributes=attributes,
        brand=product.brand,
        model=product.model,
    )
