"""live shadow preview snapshots

Revision ID: 0007_live_shadow_snapshots
Revises: 0006_live_execution_requests
Create Date: 2026-02-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007_live_shadow_snapshots"
down_revision = "0006_live_execution_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "live_shadow_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=True),
        sa.Column("portfolio_id", sa.String(length=36), nullable=True),
        sa.Column("allocation_amount", sa.Float(), nullable=True),
        sa.Column("holdings_hash", sa.String(length=64), nullable=True),
        sa.Column("holdings", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("preview", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE live_shadow_snapshots ALTER COLUMN id TYPE uuid USING id::uuid;")
        op.execute(
            "ALTER TABLE live_shadow_snapshots ALTER COLUMN portfolio_id TYPE uuid "
            "USING (CASE WHEN portfolio_id IS NULL OR portfolio_id = '' THEN NULL ELSE portfolio_id::uuid END);"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE live_shadow_snapshots ALTER COLUMN portfolio_id TYPE varchar(36) USING portfolio_id::text;"
        )
        op.execute("ALTER TABLE live_shadow_snapshots ALTER COLUMN id TYPE varchar(36) USING id::text;")
    op.drop_table("live_shadow_snapshots")
