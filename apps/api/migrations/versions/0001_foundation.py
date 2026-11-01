"""foundation: users, organizations, memberships, sessions, reset tokens, audit, products + row-level security

Revision ID: 0001
Revises:
Create Date: 2026-11-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)
# Tables whose rows belong to one organization and are hidden from other organizations by PostgreSQL itself.
RLS_TABLES = ("products", "audit_events")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("last_login_at", TZ),
    )
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("created_at", TZ, nullable=False),
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("organization_id", sa.Uuid, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
        sa.CheckConstraint("role in ('owner','admin','editor','viewer')", name="ck_membership_role"),
    )
    op.create_index("ix_memberships_organization_id", "memberships", ["organization_id"])
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("user_agent", sa.String(200), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("used_at", TZ),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("organization_id", sa.Uuid, sa.ForeignKey("organizations.id", ondelete="CASCADE")),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("details", sa.JSON, nullable=False),
        sa.Column("created_at", TZ, nullable=False),
    )
    op.create_index("ix_audit_org_created", "audit_events", ["organization_id", "created_at"])
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("organization_id", sa.Uuid, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("brand", sa.String(120), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("gtin", sa.String(14), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("price_cents", sa.Integer),
        sa.Column("cost_cents", sa.Integer),
        sa.Column("stock", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attributes", sa.JSON, nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("updated_at", TZ, nullable=False),
        sa.UniqueConstraint("organization_id", "sku", name="uq_product_org_sku"),
        sa.CheckConstraint("status in ('draft','active','archived')", name="ck_product_status"),
        sa.CheckConstraint("stock >= 0", name="ck_product_stock"),
    )
    op.create_index("ix_products_organization_id", "products", ["organization_id"])

    if op.get_bind().dialect.name == "postgresql":
        for table in RLS_TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            # FORCE: the policy also applies to the table owner (the application role). Superusers always bypass
            # RLS, so the application must never connect as a superuser (see docs/MLA_WEB_ARCHITECTURE.md).
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute("""
            CREATE POLICY tenant_isolation ON products
            USING (organization_id = nullif(current_setting('app.org_id', true), '')::uuid)
            WITH CHECK (organization_id = nullif(current_setting('app.org_id', true), '')::uuid)
        """)
        # Account-level events (organization_id NULL: login, reset) can be written without a tenant, never read.
        op.execute("""
            CREATE POLICY tenant_isolation ON audit_events
            USING (organization_id = nullif(current_setting('app.org_id', true), '')::uuid)
            WITH CHECK (organization_id IS NULL
                        OR organization_id = nullif(current_setting('app.org_id', true), '')::uuid)
        """)


def downgrade() -> None:
    for table in ("products", "audit_events", "password_reset_tokens", "auth_sessions", "memberships",
                  "organizations", "users"):
        op.drop_table(table)
