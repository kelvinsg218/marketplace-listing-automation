"""listing batches: archive and resume phase

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-02
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("listing_batches") as batch:
        batch.add_column(sa.Column("archived_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("last_phase", sa.Integer, nullable=False, server_default="1"))


def downgrade() -> None:
    with op.batch_alter_table("listing_batches") as batch:
        batch.drop_column("last_phase")
        batch.drop_column("archived_at")
