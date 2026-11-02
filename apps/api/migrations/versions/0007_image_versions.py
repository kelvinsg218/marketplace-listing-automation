"""central de imagens: image source, review status, versions, prompt and provider

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-02
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("product_images") as batch:
        batch.add_column(sa.Column("source", sa.String(12), nullable=False, server_default="upload"))
        batch.add_column(sa.Column("external_url", sa.String(500), nullable=False, server_default=""))
        batch.add_column(sa.Column("status", sa.String(10), nullable=False, server_default="approved"))
        batch.add_column(sa.Column("parent_image_id", sa.Uuid, sa.ForeignKey(
            "product_images.id", name="fk_product_images_parent", ondelete="SET NULL")))
        batch.add_column(sa.Column("prompt", sa.Text, nullable=False, server_default=""))
        batch.add_column(sa.Column("provider", sa.String(40), nullable=False, server_default=""))
        batch.add_column(sa.Column("reviewed_by", sa.Uuid, sa.ForeignKey(
            "users.id", name="fk_product_images_reviewed_by", ondelete="SET NULL")))
        batch.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True)))
    # Existing images: files are uploads, URL-only rows came from the Gestor de fotos.
    op.execute("UPDATE product_images SET source = 'gestor' WHERE storage_key IS NULL AND official_url <> ''")


def downgrade() -> None:
    with op.batch_alter_table("product_images") as batch:
        for col in ("reviewed_at", "reviewed_by", "provider", "prompt", "parent_image_id", "status", "external_url",
                    "source"):
            batch.drop_column(col)
