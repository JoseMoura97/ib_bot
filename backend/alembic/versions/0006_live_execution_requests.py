"""live execution requests idempotency

Revision ID: 0006_live_execution_requests
Revises: 0005_live_rebalance_audit
Create Date: 2026-02-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0006_live_execution_requests"
down_revision = "0005_live_rebalance_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "live_execution_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=True),
        sa.Column("portfolio_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False, unique=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="IN_PROGRESS"),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("request", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("result", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE live_execution_requests ALTER COLUMN id TYPE uuid USING id::uuid;")
        op.execute(
            "ALTER TABLE live_execution_requests ALTER COLUMN portfolio_id TYPE uuid "
            "USING (CASE WHEN portfolio_id IS NULL OR portfolio_id = '' THEN NULL ELSE portfolio_id::uuid END);"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE live_execution_requests ALTER COLUMN portfolio_id TYPE varchar(36) USING portfolio_id::text;"
        )
        op.execute("ALTER TABLE live_execution_requests ALTER COLUMN id TYPE varchar(36) USING id::text;")
    op.drop_table("live_execution_requests")
