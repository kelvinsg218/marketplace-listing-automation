"""ORM models. Money = integer cents. Every organization-owned table has organization_id (NOT NULL, indexed)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import JSON, BigInteger, Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy import Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mla_api.db import Base, utcnow


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class ProductStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _pk()
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)  # stored lower-case
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = _created()
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    created_at: Mapped[datetime] = _created()


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
        CheckConstraint("role in ('owner','admin','editor','viewer')", name="ck_membership_role"),
    )
    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = _created()

    organization: Mapped[Organization] = relationship(lazy="joined")
    user: Mapped[User] = relationship(lazy="joined")


class AuthSession(Base):
    """Server-side session. The cookie holds a random token; only its SHA-256 is stored."""
    __tablename__ = "auth_sessions"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user_agent: Mapped[str] = mapped_column(String(200), default="", nullable=False)

    user: Mapped[User] = relationship(lazy="joined")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    """Sensitive actions. organization_id is NULL for account-level events (login, password reset)."""
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_org_created", "organization_id", "created_at"),)
    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = _created()


class Product(Base):
    """Master catalog record (stage B subset; variations, media and compatibilities arrive in stage C)."""
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("organization_id", "sku", name="uq_product_org_sku"),
        CheckConstraint("status in ('draft','active','archived')", name="ck_product_status"),
        CheckConstraint("stock >= 0", name="ck_product_stock"),
    )
    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    brand: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    gtin: Mapped[str] = mapped_column(String(14), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    price_cents: Mapped[int | None] = mapped_column(Integer)
    cost_cents: Mapped[int | None] = mapped_column(Integer)
    stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=ProductStatus.DRAFT, nullable=False)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow,
                                                 nullable=False)


def _org_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)


def _product_fk(index: bool = True) -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=index, nullable=False)


class ProductVariant(Base):
    """A sellable variation of a master product (e.g. colour + size). Bulk sheets turn each into one row (P1 p.6)."""
    __tablename__ = "product_variants"
    __table_args__ = (UniqueConstraint("organization_id", "sku", name="uq_variant_org_sku"),
                      CheckConstraint("stock >= 0", name="ck_variant_stock"))
    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    product_id: Mapped[uuid.UUID] = _product_fk()
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # {"Cor": "Azul", "Tamanho": "M"}
    gtin: Mapped[str] = mapped_column(String(14), default="", nullable=False)
    price_cents: Mapped[int | None] = mapped_column(Integer)  # None = product price
    stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = _created()


class ProductImage(Base):
    """Catalog photo: a stored file, an official marketplace URL (Gestor de fotos, P3), or both."""
    __tablename__ = "product_images"
    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    product_id: Mapped[uuid.UUID] = _product_fk()
    variant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("product_variants.id", ondelete="SET NULL"))
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    official_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = _created()


class ProductChannelData(Base):
    """Per-marketplace data that does not belong in the master catalog (e.g. "Código de catálogo ML", P2 p.2)."""
    __tablename__ = "product_channel_data"
    __table_args__ = (UniqueConstraint("product_id", "marketplace", name="uq_channel_product_marketplace"),)
    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    product_id: Mapped[uuid.UUID] = _product_fk(index=False)
    marketplace: Mapped[str] = mapped_column(String(32), nullable=False)
    catalog_code: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    category_id: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow,
                                                 nullable=False)


class SellerAccount(Base):
    """A marketplace seller account of the organization. Official sheets are only accepted from the account that
    downloaded them (P1 p.8), so templates and batches hang off an account. No credentials are stored here."""
    __tablename__ = "seller_accounts"
    __table_args__ = (UniqueConstraint("organization_id", "marketplace", "label", name="uq_seller_org_label"),)
    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    marketplace: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    external_id: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    created_at: Mapped[datetime] = _created()


class TemplateStatus(StrEnum):
    INSPECTED = "inspected"
    INVALID = "invalid"
    ARCHIVED = "archived"


class MarketplaceTemplate(Base):
    """Official bulk-listing workbook downloaded by the user. The original bytes are stored untouched (sha256)."""
    __tablename__ = "marketplace_templates"
    __table_args__ = (UniqueConstraint("organization_id", "sha256", name="uq_template_org_sha"),)
    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    seller_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seller_accounts.id", ondelete="RESTRICT"),
                                                         nullable=False)
    marketplace: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # categories | codes | links | shopee | unknown
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    structure: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # inspector report
    deadline_text: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    deadline_date: Mapped[date | None] = mapped_column(Date)
    deadline_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _created()


class TemplateMapping(Base):
    """User-confirmed reading of one category sheet: which row holds the headers and what fills each column."""
    __tablename__ = "template_mappings"
    __table_args__ = (UniqueConstraint("template_id", "sheet_name", name="uq_mapping_template_sheet"),)
    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("marketplace_templates.id", ondelete="CASCADE"),
                                                   nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(64), nullable=False)
    header_row: Mapped[int] = mapped_column(Integer, nullable=False)
    columns: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # [{col, header, required}]
    rules: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)    # {col: {source, default}}
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow,
                                                 nullable=False)


class BatchStatus(StrEnum):
    DRAFT = "draft"
    NEEDS_FIX = "needs_fix"
    READY = "ready"
    EXPORTED = "exported"
    SENT_EXTERNAL = "sent_external"
    RESULT_RECEIVED = "result_received"
    DONE = "done"


class ListingBatch(Base):
    """One bulk-listing preparation. SENT_EXTERNAL / RESULT_RECEIVED need user confirmation or imported evidence;
    exporting a file never means the listings were published."""
    __tablename__ = "listing_batches"
    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    marketplace: Mapped[str] = mapped_column(String(32), nullable=False)
    seller_account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("seller_accounts.id",
                                                                           ondelete="SET NULL"))
    template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("marketplace_templates.id",
                                                                     ondelete="SET NULL"))
    sheet_name: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=BatchStatus.DRAFT, nullable=False)
    validation: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # last validation summary
    history: Mapped[list] = mapped_column(JSON, default=list, nullable=False)     # [{at, by, event, ...}]
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_phase: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # wizard phase 1-5 to resume
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow,
                                                 nullable=False)


class ListingBatchItem(Base):
    __tablename__ = "listing_batch_items"
    __table_args__ = (UniqueConstraint("batch_id", "product_id", name="uq_batch_product"),)
    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listing_batches.id", ondelete="CASCADE"), index=True,
                                                nullable=False)
    product_id: Mapped[uuid.UUID] = _product_fk(index=False)


class ListingRule(Base):
    """Adaptive rule (domain/adaptive_rules.py). The content lives in versions; this row is the current pointer."""
    __tablename__ = "listing_rules"
    __table_args__ = (
        CheckConstraint("scope in ('organization','account','category','template','batch')", name="ck_rule_scope"),
        CheckConstraint("status in ('active','inactive')", name="ck_rule_status"),
        Index("ix_rules_org_scope", "organization_id", "scope", "scope_ref"),
    )
    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_ref: Mapped[str] = mapped_column(String(80), default="", nullable=False)  # id or category (sheet) name
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="active", nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    origin: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)  # manual | prompt | erro
    origin_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow,
                                                 nullable=False)


class ListingRuleVersion(Base):
    __tablename__ = "listing_rule_versions"
    __table_args__ = (UniqueConstraint("rule_id", "version", name="uq_rule_version"),)
    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listing_rules.id", ondelete="CASCADE"), index=True,
                                               nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    note: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _created()


class BatchExport(Base):
    """A generated official sheet. Generating it never means the listings were published."""
    __tablename__ = "batch_exports"
    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listing_batches.id", ondelete="CASCADE"), index=True,
                                                nullable=False)
    template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("marketplace_templates.id",
                                                                     ondelete="SET NULL"))
    sheet_name: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rows: Mapped[int] = mapped_column(Integer, nullable=False)
    rules_applied: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # [[rule_id, version], ...]
    checks: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _created()


class ImportJob(Base):
    """One catalog import: uploaded file -> analysis -> dry run -> background processing -> report."""
    __tablename__ = "import_jobs"
    __table_args__ = (CheckConstraint(
        "status in ('analyzed','planned','running','done','failed','cancelled')", name="ck_import_status"),)
    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    format: Mapped[str] = mapped_column(String(8), nullable=False)
    sheet: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    mapping: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)    # {column header: field key}
    options: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)    # {update_existing: bool}
    totals: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)     # rows/created/updated/...
    report: Mapped[list] = mapped_column(JSON, default=list, nullable=False)     # per-row issues (capped)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _created()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportProfile(Base):
    """Saved column mapping ("perfil de importação") reused for files with the same headers."""
    __tablename__ = "import_profiles"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_import_profile_name"),)
    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    mapping: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = _created()


class Category(Base):
    """Internal category (organization tree), independent of marketplace categories. Keywords drive the
    deterministic classifier (domain/classifier.py). The ML category is user-provided and flagged unconfirmed."""
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("organization_id", "parent_id", "name", name="uq_category_name"),)
    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    keywords: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # {phrases, words, exclude}
    ml_category_id: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    ml_category_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = _created()


class ProductClassification(Base):
    """Classification of one product: suggestion (with evidence) or a manual confirmation that is never
    overwritten automatically."""
    __tablename__ = "product_classifications"
    __table_args__ = (UniqueConstraint("product_id", name="uq_classification_product"),
                      CheckConstraint("status in ('suggested','unclassified','confirmed')", name="ck_class_status"))
    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    product_id: Mapped[uuid.UUID] = _product_fk(index=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(14), nullable=False)
    confidence: Mapped[str] = mapped_column(String(8), default="baixa", nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    evidence: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow,
                                                 nullable=False)


# Tables protected by PostgreSQL row-level security (migrations 0001-0005). New organization-owned tables must be
# added here AND get a policy in their migration; tests/test_isolation.py checks the list against the metadata.
TENANT_TABLES = ("products", "audit_events", "product_variants", "product_images", "product_channel_data",
                 "seller_accounts", "marketplace_templates", "template_mappings", "listing_batches",
                 "listing_batch_items", "listing_rules", "listing_rule_versions", "batch_exports", "import_jobs",
                 "import_profiles", "categories", "product_classifications")
