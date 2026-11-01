"""adaptive rules (versioned) and batch exports

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)
NEW_TABLES = ("listing_rules", "listing_rule_versions", "batch_exports")


def _org():
    return sa.Column("organization_id", sa.Uuid, sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=False)


def upgrade() -> None:
    op.create_table(
        "listing_rules",
        sa.Column("id", sa.Uuid, primary_key=True), _org(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("scope_ref", sa.String(80), nullable=False),
        sa.Column("priority", sa.Integer, nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("current_version", sa.Integer, nullable=False),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("origin_text", sa.Text, nullable=False),
        sa.Column("created_by", sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("updated_at", TZ, nullable=False),
        sa.CheckConstraint("scope in ('organization','account','category','template','batch')", name="ck_rule_scope"),
        sa.CheckConstraint("status in ('active','inactive')", name="ck_rule_status"),
    )
    op.create_index("ix_listing_rules_organization_id", "listing_rules", ["organization_id"])
    op.create_index("ix_rules_org_scope", "listing_rules", ["organization_id", "scope", "scope_ref"])

    op.create_table(
        "listing_rule_versions",
        sa.Column("id", sa.Uuid, primary_key=True), _org(),
        sa.Column("rule_id", sa.Uuid, sa.ForeignKey("listing_rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("definition", sa.JSON, nullable=False),
        sa.Column("note", sa.String(300), nullable=False),
        sa.Column("author_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", TZ, nullable=False),
        sa.UniqueConstraint("rule_id", "version", name="uq_rule_version"),
    )
    op.create_index("ix_listing_rule_versions_organization_id", "listing_rule_versions", ["organization_id"])
    op.create_index("ix_listing_rule_versions_rule_id", "listing_rule_versions", ["rule_id"])

    op.create_table(
        "batch_exports",
        sa.Column("id", sa.Uuid, primary_key=True), _org(),
        sa.Column("batch_id", sa.Uuid, sa.ForeignKey("listing_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", sa.Uuid, sa.ForeignKey("marketplace_templates.id", ondelete="SET NULL")),
        sa.Column("sheet_name", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("rows", sa.Integer, nullable=False),
        sa.Column("rules_applied", sa.JSON, nullable=False),
        sa.Column("checks", sa.JSON, nullable=False),
        sa.Column("created_by", sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", TZ, nullable=False),
    )
    op.create_index("ix_batch_exports_organization_id", "batch_exports", ["organization_id"])
    op.create_index("ix_batch_exports_batch_id", "batch_exports", ["batch_id"])

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
