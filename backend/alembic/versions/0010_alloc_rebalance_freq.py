"""rebalance_frequency on portfolio_allocations

Revision ID: 0010_alloc_rebalance_freq
Revises: 0009_system_state
Create Date: 2026-05-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_alloc_rebalance_freq"
down_revision = "0009_system_state"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns(table)]
    return column in cols


def upgrade() -> None:
    # Idempotent: the column may already exist (added out-of-band before this
    # migration ran), so only add it when missing.
    if not _has_column("portfolio_allocations", "rebalance_frequency"):
        op.add_column(
            "portfolio_allocations",
            sa.Column("rebalance_frequency", sa.String(16), nullable=True),
        )


def downgrade() -> None:
    if _has_column("portfolio_allocations", "rebalance_frequency"):
        op.drop_column("portfolio_allocations", "rebalance_frequency")
