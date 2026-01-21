"""init tables

Revision ID: 0001_init
Revises:
Create Date: 2026-01-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("name", sa.String(length=200), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "portfolios",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("default_cash", sa.Float(), nullable=False, server_default=sa.text("100000")),
        sa.Column("settings", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "portfolio_strategies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("portfolio_id", sa.String(length=36), nullable=False),
        sa.Column("strategy_name", sa.String(length=200), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("weight", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("overrides", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index("uq_portfolio_strategy", "portfolio_strategies", ["portfolio_id", "strategy_name"], unique=True)

    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("progress", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.String(length=2000), nullable=True),
    )

    op.create_table(
        "strategy_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("strategy_name", sa.String(length=200), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("artifacts", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "portfolio_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("portfolio_id", sa.String(length=36), nullable=False),
        sa.Column("mode", sa.String(length=50), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("artifacts", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("portfolio_results")
    op.drop_table("strategy_results")
    op.drop_table("runs")
    op.drop_index("uq_portfolio_strategy", table_name="portfolio_strategies")
    op.drop_table("portfolio_strategies")
    op.drop_table("portfolios")
    op.drop_table("strategies")
