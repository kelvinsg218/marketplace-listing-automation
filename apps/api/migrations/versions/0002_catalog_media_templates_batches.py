"""catalog variants, images, channel data, seller accounts, official templates, mappings, listing batches

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)
NEW_TABLES = ("product_variants", "product_images", "product_channel_data", "seller_accounts",
              "marketplace_templates", "template_mappings", "listing_batches", "listing_batch_items")


def _org():
    return sa.Column("organization_id", sa.Uuid, sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=False)


def _product():
    return sa.Column("product_id", sa.Uuid, sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "product_variants",
        sa.Column("id", sa.Uuid, primary_key=True), _org(), _product(),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("attributes", sa.JSON, nullable=False),
        sa.Column("gtin", sa.String(14), nullable=False),
        sa.Column("price_cents", sa.Integer),
        sa.Column("stock", sa.Integer, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.UniqueConstraint("organization_id", "sku", name="uq_variant_org_sku"),
        sa.CheckConstraint("stock >= 0", name="ck_variant_stock"),
    )
    op.create_index("ix_product_variants_organization_id", "product_variants", ["organization_id"])
    op.create_index("ix_product_variants_product_id", "product_variants", ["product_id"])

    op.create_table(
        "product_images",
        sa.Column("id", sa.Uuid, primary_key=True), _org(), _product(),
        sa.Column("variant_id", sa.Uuid, sa.ForeignKey("product_variants.id", ondelete="SET NULL")),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("storage_key", sa.String(255)),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("official_url", sa.String(500), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
    )
    op.create_index("ix_product_images_organization_id", "product_images", ["organization_id"])
    op.create_index("ix_product_images_product_id", "product_images", ["product_id"])

    op.create_table(
        "product_channel_data",
        sa.Column("id", sa.Uuid, primary_key=True), _org(), _product(),
        sa.Column("marketplace", sa.String(32), nullable=False),
        sa.Column("catalog_code", sa.String(40), nullable=False),
        sa.Column("category_id", sa.String(40), nullable=False),
        sa.Column("updated_at", TZ, nullable=False),
        sa.UniqueConstraint("product_id", "marketplace", name="uq_channel_product_marketplace"),
    )
    op.create_index("ix_product_channel_data_organization_id", "product_channel_data", ["organization_id"])

    op.create_table(
        "seller_accounts",
        sa.Column("id", sa.Uuid, primary_key=True), _org(),
        sa.Column("marketplace", sa.String(32), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("external_id", sa.String(40), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.UniqueConstraint("organization_id", "marketplace", "label", name="uq_seller_org_label"),
    )
    op.create_index("ix_seller_accounts_organization_id", "seller_accounts", ["organization_id"])

    op.create_table(
        "marketplace_templates",
        sa.Column("id", sa.Uuid, primary_key=True), _org(),
        sa.Column("seller_account_id", sa.Uuid, sa.ForeignKey("seller_accounts.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("marketplace", sa.String(32), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("structure", sa.JSON, nullable=False),
        sa.Column("deadline_text", sa.String(200), nullable=False),
        sa.Column("deadline_date", sa.Date),
        sa.Column("deadline_confirmed", sa.Boolean, nullable=False),
        sa.Column("uploaded_by", sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", TZ, nullable=False),
        sa.UniqueConstraint("organization_id", "sha256", name="uq_template_org_sha"),
    )
    op.create_index("ix_marketplace_templates_organization_id", "marketplace_templates", ["organization_id"])

    op.create_table(
        "template_mappings",
        sa.Column("id", sa.Uuid, primary_key=True), _org(),
        sa.Column("template_id", sa.Uuid, sa.ForeignKey("marketplace_templates.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("sheet_name", sa.String(64), nullable=False),
        sa.Column("header_row", sa.Integer, nullable=False),
        sa.Column("columns", sa.JSON, nullable=False),
        sa.Column("rules", sa.JSON, nullable=False),
        sa.Column("updated_at", TZ, nullable=False),
        sa.UniqueConstraint("template_id", "sheet_name", name="uq_mapping_template_sheet"),
    )
    op.create_index("ix_template_mappings_organization_id", "template_mappings", ["organization_id"])

    op.create_table(
        "listing_batches",
        sa.Column("id", sa.Uuid, primary_key=True), _org(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("marketplace", sa.String(32), nullable=False),
        sa.Column("seller_account_id", sa.Uuid, sa.ForeignKey("seller_accounts.id", ondelete="SET NULL")),
        sa.Column("template_id", sa.Uuid, sa.ForeignKey("marketplace_templates.id", ondelete="SET NULL")),
        sa.Column("sheet_name", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("validation", sa.JSON, nullable=False),
        sa.Column("history", sa.JSON, nullable=False),
        sa.Column("created_by", sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("updated_at", TZ, nullable=False),
    )
    op.create_index("ix_listing_batches_organization_id", "listing_batches", ["organization_id"])

    op.create_table(
        "listing_batch_items",
        sa.Column("id", sa.Uuid, primary_key=True), _org(),
        sa.Column("batch_id", sa.Uuid, sa.ForeignKey("listing_batches.id", ondelete="CASCADE"), nullable=False),
        _product(),
        sa.UniqueConstraint("batch_id", "product_id", name="uq_batch_product"),
    )
    op.create_index("ix_listing_batch_items_organization_id", "listing_batch_items", ["organization_id"])
    op.create_index("ix_listing_batch_items_batch_id", "listing_batch_items", ["batch_id"])

    if op.get_bind().dialect.name == "postgresql":
        for table in NEW_TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(f"""
                CREATE POLICY tenant_isolation ON {table}
                USING (organization_id = nullif(current_setting('app.org_id', true), '')::uuid)
                WITH CHECK (organization_id = nullif(current_setting('app.org_id', true), '')::uuid)
            """)


def downgrade() -> None:
    for table in reversed(NEW_TABLES):
        op.drop_table(table)
