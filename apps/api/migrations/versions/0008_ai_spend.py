"""estúdio de IA: installation-wide spend counter and per-image cost/usage

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-02
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Not organization-owned (the provider key and budget belong to the operator), so no RLS policy here.
    op.create_table(
        "ai_spend",
        sa.Column("provider", sa.String(40), primary_key=True),
        sa.Column("spent_micro_usd", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("reserved_micro_usd", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("calls", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    with op.batch_alter_table("product_images") as batch:
        batch.add_column(sa.Column("cost_micro_usd", sa.BigInteger, nullable=False, server_default="0"))
        batch.add_column(sa.Column("ai_usage", sa.JSON, nullable=False, server_default="{}"))


def downgrade() -> None:
    with op.batch_alter_table("product_images") as batch:
        batch.drop_column("ai_usage")
        batch.drop_column("cost_micro_usd")
    op.drop_table("ai_spend")
