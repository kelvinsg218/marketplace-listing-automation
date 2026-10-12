"""Plain data objects shared by persistence, services and UI."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mla.core.enums import (
    CatalogStatus, Condition, ItemStatus, JobStatus, ListingStatus, Marketplace,
)


@dataclass
class ProductImage:
    filename: str  # relative to AppPaths.images
    position: int = 0
    is_main: bool = False
    width: int = 0
    height: int = 0
    size_bytes: int = 0
    sha256: str = ""
    id: int | None = None
    product_id: int | None = None


@dataclass
class ProductVariant:
    name: str
    attributes: dict[str, str] = field(default_factory=dict)
    sku: str | None = None
    price_cents: int | None = None
    stock: int = 0
    position: int = 0
    id: int | None = None
    product_id: int | None = None


@dataclass
class ProductMarketplaceData:
    marketplace: Marketplace
    enabled: bool = False
    price_cents: int | None = None  # overrides Product.price_cents when set
    category_id: str = ""
    listing_type: str = ""
    attributes: dict[str, str] = field(default_factory=dict)
    product_id: int | None = None


@dataclass
class Product:
    internal_name: str
    sku: str
    title: str = ""
    category: str = ""
    subcategory: str = ""
    brand: str = ""
    model: str = ""
    condition: Condition = Condition.NEW
    description: str = ""
    features: str = ""
    material: str = ""
    package_contents: str = ""
    warranty: str = ""
    price_cents: int | None = None
    stock: int = 0
    weight_g: int | None = None
    length_mm: int | None = None
    width_mm: int | None = None
    height_mm: int | None = None
    package_type: str = ""
    availability_days: int | None = None
    shipping_notes: str = ""
    status: CatalogStatus = CatalogStatus.DRAFT
    images: list[ProductImage] = field(default_factory=list)
    variants: list[ProductVariant] = field(default_factory=list)
    marketplace_data: dict[Marketplace, ProductMarketplaceData] = field(default_factory=dict)
    id: int | None = None
    created_at: str = ""
    updated_at: str = ""

    @property
    def main_image(self) -> ProductImage | None:
        for image in self.images:
            if image.is_main:
                return image
        return self.images[0] if self.images else None

    def enabled_marketplaces(self) -> list[Marketplace]:
        return [m for m, data in self.marketplace_data.items() if data.enabled]

    def price_for(self, marketplace: Marketplace) -> int | None:
        data = self.marketplace_data.get(marketplace)
        if data and data.price_cents is not None:
            return data.price_cents
        return self.price_cents


@dataclass
class ProductSummary:
    """Lightweight row for lists and tables."""
    id: int
    internal_name: str
    title: str
    sku: str
    category: str
    price_cents: int | None
    stock: int
    status: CatalogStatus
    image_count: int
    main_image: str | None
    updated_at: str
    marketplaces: list[Marketplace] = field(default_factory=list)


@dataclass
class ProductGroup:
    name: str
    description: str = ""
    marketplaces: list[Marketplace] = field(default_factory=list)
    product_ids: list[int] = field(default_factory=list)
    id: int | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class MarketplaceAccount:
    marketplace: Marketplace
    label: str
    profile_dir: str = ""
    is_active: bool = True
    id: int | None = None
    created_at: str = ""


@dataclass
class Job:
    label: str
    kind: str = "product"  # product | group | batch
    group_id: int | None = None
    status: JobStatus = JobStatus.PENDING
    id: int | None = None
    created_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None


@dataclass
class JobItem:
    job_id: int
    product_id: int
    marketplace: Marketplace
    account_id: int
    position: int = 0
    status: ItemStatus = ItemStatus.QUEUED
    step: str = ""
    attempts: int = 0
    error: str = ""
    external_id: str = ""
    url: str = ""
    id: int | None = None
    created_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    # denormalised for display
    product_name: str = ""
    sku: str = ""
    account_label: str = ""


@dataclass
class Listing:
    product_id: int
    marketplace: Marketplace
    account_id: int
    status: ListingStatus
    external_id: str = ""
    url: str = ""
    published_at: str | None = None
    last_item_id: int | None = None
    id: int | None = None
    updated_at: str = ""


@dataclass
class ExecutionLog:
    level: str
    message: str
    step: str = ""
    job_id: int | None = None
    item_id: int | None = None
    product_id: int | None = None
    marketplace: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    screenshot: str = ""
    id: int | None = None
    created_at: str = ""
