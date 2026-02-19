"""paper snapshots and rebalance logs

Revision ID: 0008_paper_snapshots_rebalance_logs
Revises: 0007_live_shadow_snapshots
Create Date: 2026-02-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008_paper_snapshots_rebalance_logs"
down_revision = "0007_live_shadow_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "paper_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("paper_cash.id", ondelete="CASCADE"), nullable=False),
        sa.Column("portfolio_id", sa.String(length=36), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("cash", sa.Float(), nullable=False),
        sa.Column("equity", sa.Float(), nullable=False),
        sa.Column("positions_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )

    op.create_table(
        "paper_rebalance_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("paper_cash.id", ondelete="CASCADE"), nullable=False),
        sa.Column("portfolio_id", sa.String(length=36), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="SUCCESS"),
        sa.Column("n_orders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )

    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE paper_snapshots ALTER COLUMN portfolio_id TYPE uuid "
            "USING (CASE WHEN portfolio_id IS NULL OR portfolio_id = '' THEN NULL ELSE portfolio_id::uuid END);"
        )
        op.execute(
            "ALTER TABLE paper_rebalance_logs ALTER COLUMN portfolio_id TYPE uuid "
            "USING (CASE WHEN portfolio_id IS NULL OR portfolio_id = '' THEN NULL ELSE portfolio_id::uuid END);"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE paper_snapshots ALTER COLUMN portfolio_id TYPE varchar(36) USING portfolio_id::text;")
        op.execute("ALTER TABLE paper_rebalance_logs ALTER COLUMN portfolio_id TYPE varchar(36) USING portfolio_id::text;")
    op.drop_table("paper_rebalance_logs")
    op.drop_table("paper_snapshots")
