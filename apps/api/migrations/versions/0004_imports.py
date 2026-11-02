"""catalog import jobs and saved import profiles

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)
NEW_TABLES = ("import_jobs", "import_profiles")


def _org():
    return sa.Column("organization_id", sa.Uuid, sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=False)


def upgrade() -> None:
    op.create_table(
        "import_jobs",
        sa.Column("id", sa.Uuid, primary_key=True), _org(),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column("format", sa.String(8), nullable=False),
        sa.Column("sheet", sa.String(120), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("mapping", sa.JSON, nullable=False),
        sa.Column("options", sa.JSON, nullable=False),
        sa.Column("totals", sa.JSON, nullable=False),
        sa.Column("report", sa.JSON, nullable=False),
        sa.Column("cancel_requested", sa.Boolean, nullable=False),
        sa.Column("created_by", sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("finished_at", TZ),
        sa.CheckConstraint("status in ('analyzed','planned','running','done','failed','cancelled')",
                           name="ck_import_status"),
    )
    op.create_index("ix_import_jobs_organization_id", "import_jobs", ["organization_id"])
    op.create_table(
        "import_profiles",
        sa.Column("id", sa.Uuid, primary_key=True), _org(),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("mapping", sa.JSON, nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_import_profile_name"),
    )
    op.create_index("ix_import_profiles_organization_id", "import_profiles", ["organization_id"])
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
