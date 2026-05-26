"""altdata point-in-time snapshots

Revision ID: 0011_altdata_snapshots
Revises: 0010_alloc_rebalance_freq
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011_altdata_snapshots"
down_revision = "0010_alloc_rebalance_freq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "altdata_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("n_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("payload", JSONB(), nullable=True),
        sa.UniqueConstraint("source", "as_of_date", name="uq_altdata_source_date"),
    )
    op.create_index("ix_altdata_snapshots_source", "altdata_snapshots", ["source"])
    op.create_index("ix_altdata_snapshots_as_of_date", "altdata_snapshots", ["as_of_date"])
    op.create_index("ix_altdata_snapshots_content_hash", "altdata_snapshots", ["content_hash"])


def downgrade() -> None:
    op.drop_index("ix_altdata_snapshots_content_hash", table_name="altdata_snapshots")
    op.drop_index("ix_altdata_snapshots_as_of_date", table_name="altdata_snapshots")
    op.drop_index("ix_altdata_snapshots_source", table_name="altdata_snapshots")
    op.drop_table("altdata_snapshots")
