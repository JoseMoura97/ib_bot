"""paper accounts + orders + allocations

Revision ID: 0004_paper_allocations
Revises: 0003_fix_uuid_columns
Create Date: 2026-01-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_paper_allocations"
down_revision = "0003_fix_uuid_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # paper_cash -> treat as PaperAccount; add name + created_at.
    with op.batch_alter_table("paper_cash") as batch:
        batch.add_column(
            sa.Column(
                "name",
                sa.String(length=200),
                nullable=False,
                server_default=sa.text("'Default Paper Account'"),
            )
        )
        batch.add_column(sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))

    # Scope positions/trades to account_id (default 1 for existing data).
    with op.batch_alter_table("paper_positions") as batch:
        batch.add_column(sa.Column("account_id", sa.Integer(), nullable=False, server_default="1"))
        # SQLite can't add FKs reliably without table rebuild; batch mode handles rebuild where possible.
        batch.create_foreign_key("fk_paper_positions_account", "paper_cash", ["account_id"], ["id"], ondelete="CASCADE")
        batch.create_unique_constraint("uq_paper_position_account_ticker", ["account_id", "ticker"])

    with op.batch_alter_table("paper_trades") as batch:
        batch.add_column(sa.Column("account_id", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("order_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key("fk_paper_trades_account", "paper_cash", ["account_id"], ["id"], ondelete="CASCADE")

    # New: paper orders table.
    op.create_table(
        "paper_orders",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("filled_at", sa.DateTime(), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("order_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("fill_price", sa.Float(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.ForeignKeyConstraint(["account_id"], ["paper_cash.id"], ondelete="CASCADE"),
    )

    # New: allocations ledger.
    op.create_table(
        "portfolio_allocations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("portfolio_id", sa.String(length=36), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_portfolio_allocations_portfolio_id", "portfolio_allocations", ["portfolio_id"])

    # Postgres: convert uuid-ish columns to UUID.
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE paper_orders ALTER COLUMN id TYPE uuid USING id::uuid;")
        op.execute("ALTER TABLE paper_trades ALTER COLUMN order_id TYPE uuid USING (CASE WHEN order_id IS NULL OR order_id = '' THEN NULL ELSE order_id::uuid END);")
        op.execute("ALTER TABLE portfolio_allocations ALTER COLUMN id TYPE uuid USING id::uuid;")
        op.execute("ALTER TABLE portfolio_allocations ALTER COLUMN portfolio_id TYPE uuid USING portfolio_id::uuid;")


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE portfolio_allocations ALTER COLUMN portfolio_id TYPE varchar(36) USING portfolio_id::text;")
        op.execute("ALTER TABLE portfolio_allocations ALTER COLUMN id TYPE varchar(36) USING id::text;")
        op.execute("ALTER TABLE paper_trades ALTER COLUMN order_id TYPE varchar(36) USING order_id::text;")
        op.execute("ALTER TABLE paper_orders ALTER COLUMN id TYPE varchar(36) USING id::text;")

    op.drop_index("ix_portfolio_allocations_portfolio_id", table_name="portfolio_allocations")
    op.drop_table("portfolio_allocations")
    op.drop_table("paper_orders")

    with op.batch_alter_table("paper_trades") as batch:
        batch.drop_constraint("fk_paper_trades_account", type_="foreignkey")
        batch.drop_column("order_id")
        batch.drop_column("account_id")

    with op.batch_alter_table("paper_positions") as batch:
        batch.drop_constraint("uq_paper_position_account_ticker", type_="unique")
        batch.drop_constraint("fk_paper_positions_account", type_="foreignkey")
        batch.drop_column("account_id")

    with op.batch_alter_table("paper_cash") as batch:
        batch.drop_column("created_at")
        batch.drop_column("name")

