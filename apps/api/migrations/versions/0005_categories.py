"""internal categories and product classifications

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-02
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)
NEW_TABLES = ("categories", "product_classifications")


def _org():
    return sa.Column("organization_id", sa.Uuid, sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=False)


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Uuid, primary_key=True), _org(),
        sa.Column("parent_id", sa.Uuid, sa.ForeignKey("categories.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("keywords", sa.JSON, nullable=False),
        sa.Column("ml_category_id", sa.String(40), nullable=False),
        sa.Column("ml_category_confirmed", sa.Boolean, nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.UniqueConstraint("organization_id", "parent_id", "name", name="uq_category_name"),
    )
    op.create_index("ix_categories_organization_id", "categories", ["organization_id"])
    op.create_table(
        "product_classifications",
        sa.Column("id", sa.Uuid, primary_key=True), _org(),
        sa.Column("product_id", sa.Uuid, sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", sa.Uuid, sa.ForeignKey("categories.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(14), nullable=False),
        sa.Column("confidence", sa.String(8), nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("evidence", sa.JSON, nullable=False),
        sa.Column("decided_by", sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_at", TZ, nullable=False),
        sa.UniqueConstraint("product_id", name="uq_classification_product"),
        sa.CheckConstraint("status in ('suggested','unclassified','confirmed')", name="ck_class_status"),
    )
    op.create_index("ix_product_classifications_organization_id", "product_classifications", ["organization_id"])
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
