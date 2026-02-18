"""live rebalance audit table

Revision ID: 0005_live_rebalance_audit
Revises: 0004_paper_allocations
Create Date: 2026-01-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_live_rebalance_audit"
down_revision = "0004_paper_allocations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "live_rebalance_audit",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="OK"),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("account_id", sa.String(length=64), nullable=True),
        sa.Column("portfolio_id", sa.String(length=36), nullable=True),
        sa.Column("allocation_amount", sa.Float(), nullable=True),
        sa.Column("max_notional_usd", sa.Float(), nullable=True),
        sa.Column("max_percent_nlv", sa.Float(), nullable=True),
        sa.Column("max_orders", sa.Integer(), nullable=True),
        sa.Column("allow_short", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("request", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("orders", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE live_rebalance_audit ALTER COLUMN id TYPE uuid USING id::uuid;")
        op.execute("ALTER TABLE live_rebalance_audit ALTER COLUMN portfolio_id TYPE uuid USING (CASE WHEN portfolio_id IS NULL OR portfolio_id = '' THEN NULL ELSE portfolio_id::uuid END);")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE live_rebalance_audit ALTER COLUMN portfolio_id TYPE varchar(36) USING portfolio_id::text;")
        op.execute("ALTER TABLE live_rebalance_audit ALTER COLUMN id TYPE varchar(36) USING id::text;")
    op.drop_table("live_rebalance_audit")
