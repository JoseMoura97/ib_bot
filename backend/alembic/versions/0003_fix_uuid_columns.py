"""fix uuid column types for postgres

Revision ID: 0003_fix_uuid_columns
Revises: 0002_paper_ib
Create Date: 2026-01-20
"""

from __future__ import annotations

from alembic import op


revision = "0003_fix_uuid_columns"
down_revision = "0002_paper_ib"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Core tables
    op.execute("ALTER TABLE portfolios ALTER COLUMN id TYPE uuid USING id::uuid;")
    op.execute(
        "ALTER TABLE portfolio_strategies ALTER COLUMN portfolio_id TYPE uuid USING portfolio_id::uuid;"
    )
    op.execute("ALTER TABLE runs ALTER COLUMN id TYPE uuid USING id::uuid;")
    op.execute("ALTER TABLE strategy_results ALTER COLUMN run_id TYPE uuid USING run_id::uuid;")
    op.execute("ALTER TABLE portfolio_results ALTER COLUMN run_id TYPE uuid USING run_id::uuid;")
    op.execute(
        "ALTER TABLE portfolio_results ALTER COLUMN portfolio_id TYPE uuid USING portfolio_id::uuid;"
    )

    # IB audit tables
    op.execute("ALTER TABLE ib_orders ALTER COLUMN id TYPE uuid USING id::uuid;")
    op.execute("ALTER TABLE ib_trades ALTER COLUMN id TYPE uuid USING id::uuid;")
    op.execute(
        """
        ALTER TABLE ib_trades
        ALTER COLUMN order_id TYPE uuid
        USING (
          CASE
            WHEN order_id IS NULL OR order_id = '' THEN NULL
            ELSE order_id::uuid
          END
        );
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE ib_trades ALTER COLUMN order_id TYPE varchar(36) USING order_id::text;")
    op.execute("ALTER TABLE ib_trades ALTER COLUMN id TYPE varchar(36) USING id::text;")
    op.execute("ALTER TABLE ib_orders ALTER COLUMN id TYPE varchar(36) USING id::text;")

    op.execute("ALTER TABLE portfolio_results ALTER COLUMN portfolio_id TYPE varchar(36) USING portfolio_id::text;")
    op.execute("ALTER TABLE portfolio_results ALTER COLUMN run_id TYPE varchar(36) USING run_id::text;")
    op.execute("ALTER TABLE strategy_results ALTER COLUMN run_id TYPE varchar(36) USING run_id::text;")
    op.execute("ALTER TABLE runs ALTER COLUMN id TYPE varchar(36) USING id::text;")
    op.execute("ALTER TABLE portfolio_strategies ALTER COLUMN portfolio_id TYPE varchar(36) USING portfolio_id::text;")
    op.execute("ALTER TABLE portfolios ALTER COLUMN id TYPE varchar(36) USING id::text;")

