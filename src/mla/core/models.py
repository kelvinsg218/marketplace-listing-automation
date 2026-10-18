"""Plain data objects shared by persistence, services and UI."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mla.core.enums import (
    CatalogStatus, CommercialStatus, Condition, ConnectionStatus, DataSource, ImportAction, ImportStatus,
    ItemStatus, JobStatus, ListingStatus, Marketplace, Verification,
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
    variant: str = ""        # name of the variation this image shows ("" = whole product)
    original_name: str = ""  # file name in the source (import/association by name)
    id: int | None = None
    product_id: int | None = None


@dataclass
class ProductFile:
    """Technical file (manual, datasheet) stored content-addressed under AppPaths.files."""
    filename: str
    original_name: str = ""
    size_bytes: int = 0
    sha256: str = ""
    position: int = 0
    id: int | None = None
    product_id: int | None = None


@dataclass
class MissingMedia:
    """A file a source referenced but MLA could not find; resolved later by name."""
    reference: str
    kind: str = "image"  # image | file
    origin: str = ""
    id: int | None = None
    created_at: str = ""


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
    # master catalog (migration 0004); all optional
    commercial_name: str = ""
    manufacturer_code: str = ""
    gtin: str = ""
    supplier: str = ""
    cost_cents: int | None = None
    promo_price_cents: int | None = None
    min_stock: int | None = None
    unit: str = ""
    commercial_status: CommercialStatus = CommercialStatus.ACTIVE
    original_description: str = ""  # text exactly as received from the client's base
    technical_description: str = ""
    color: str = ""
    specs: dict[str, str] = field(default_factory=dict)
    custom_attributes: dict[str, str] = field(default_factory=dict)
    manufacturer_refs: str = ""
    internal_notes: str = ""
    source: str = ""  # where the record came from (e.g. "Importação #3")
    images: list[ProductImage] = field(default_factory=list)
    variants: list[ProductVariant] = field(default_factory=list)
    marketplace_data: dict[Marketplace, ProductMarketplaceData] = field(default_factory=dict)
    files: list[ProductFile] = field(default_factory=list)
    missing_media: list[MissingMedia] = field(default_factory=list)
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
    brand: str = ""
    gtin: str = ""
    commercial_status: CommercialStatus = CommercialStatus.ACTIVE
    compat_count: int = 0
    missing_media: int = 0


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
    seller_url: str = ""
    internal_id: str = ""
    is_default: bool = False
    connection_status: ConnectionStatus = ConnectionStatus.UNKNOWN
    connection_message: str = ""
    connection_checked_at: str | None = None
    detected_identity: str = ""
    last_connected_at: str | None = None


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
    """One offer of a master product on one marketplace account.

    Content fields are overrides: "" / None / [] mean "use the master product".
    """
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
    title: str = ""
    description: str = ""
    price_cents: int | None = None
    stock: int | None = None
    category_id: str = ""
    listing_type: str = ""
    attributes: dict[str, str] = field(default_factory=dict)
    image_files: list[str] = field(default_factory=list)  # chosen product images, in order
    notes: str = ""
    approved_at: str | None = None
    approved_hash: str = ""
    created_at: str = ""


@dataclass
class ListingRow:
    """Listing joined with its product and account, for tables."""
    listing: Listing
    product_name: str
    sku: str
    title: str  # effective title
    price_cents: int | None  # effective price
    account_label: str
    main_image: str | None
    product_status: CatalogStatus


@dataclass
class Compatibility:
    product_id: int | None
    model: str
    brand: str = ""
    version: str = ""
    year_from: int | None = None
    year_to: int | None = None
    reference_code: str = ""
    notes: str = ""
    source: DataSource = DataSource.CLIENT
    source_detail: str = ""
    verification: Verification = Verification.UNVERIFIED
    id: int | None = None
    created_at: str = ""
    updated_at: str = ""
    # denormalised for display
    product_name: str = ""
    sku: str = ""

    def years(self) -> str:
        if self.year_from and self.year_to:
            return str(self.year_from) if self.year_from == self.year_to else f"{self.year_from}–{self.year_to}"
        if self.year_from:
            return f"{self.year_from} em diante"
        if self.year_to:
            return f"até {self.year_to}"
        return ""


@dataclass
class ImportBatch:
    source_name: str
    format: str
    target: str = "products"  # products | compatibility | images
    status: ImportStatus = ImportStatus.PLANNING
    source_path: str = ""
    source_sha256: str = ""
    mapping: dict[str, str] = field(default_factory=dict)  # source column -> target field
    options: dict[str, Any] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    message: str = ""
    staging_dir: str = ""
    id: int | None = None
    created_at: str = ""
    planned_at: str | None = None
    finished_at: str | None = None


@dataclass
class ImportRow:
    batch_id: int
    row_no: int
    action: ImportAction
    decision: str = "skip"  # create | update | skip
    sku: str = ""
    name: str = ""
    product_id: int | None = None
    parent_sku: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    changes: list[dict[str, str]] = field(default_factory=list)  # {field, label, old, new}
    issues: list[dict[str, str]] = field(default_factory=list)   # {severity, message}
    media: list[dict[str, str]] = field(default_factory=list)    # {ref, kind, path, status}
    outcome: str = ""
    id: int | None = None


@dataclass
class ImportTemplate:
    name: str
    target: str = "products"
    headers: list[str] = field(default_factory=list)
    mapping: dict[str, str] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    id: int | None = None
    created_at: str = ""
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
