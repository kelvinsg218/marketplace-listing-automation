"""mercado livre official oauth: encrypted connections per seller account and pending authorization states

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-02
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)
NEW_TABLES = ("marketplace_connections", "oauth_states")


def _org():
    return sa.Column("organization_id", sa.Uuid, sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=False)


def _account():
    return sa.Column("seller_account_id", sa.Uuid, sa.ForeignKey("seller_accounts.id", ondelete="CASCADE"),
                     nullable=False)


def upgrade() -> None:
    op.create_table(
        "marketplace_connections",
        sa.Column("id", sa.Uuid, primary_key=True),
        _org(),
        _account(),
        sa.Column("marketplace", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("remote_user_id", sa.String(40)),
        sa.Column("nickname", sa.String(120), nullable=False),
        sa.Column("scope", sa.String(255), nullable=False),
        sa.Column("access_token_enc", sa.Text, nullable=False),
        sa.Column("refresh_token_enc", sa.Text, nullable=False),
        sa.Column("expires_at", TZ),
        sa.Column("connected_by", sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("connected_at", TZ),
        sa.Column("refreshed_at", TZ),
        sa.Column("checked_at", TZ),
        sa.Column("last_error", sa.String(300), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.UniqueConstraint("seller_account_id", name="uq_connection_account"),
        sa.UniqueConstraint("organization_id", "marketplace", "remote_user_id", name="uq_connection_remote"),
    )
    op.create_index("ix_marketplace_connections_organization_id", "marketplace_connections", ["organization_id"])
    op.create_table(
        "oauth_states",
        sa.Column("id", sa.Uuid, primary_key=True),
        _org(),
        _account(),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("verifier_enc", sa.Text, nullable=False),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("used_at", TZ),
        sa.Column("created_at", TZ, nullable=False),
    )
    op.create_index("ix_oauth_states_organization_id", "oauth_states", ["organization_id"])
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
