from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base
from app.db.types import GUID


def _json_type():
    return JSON().with_variant(JSONB, "postgresql")


def _uuid_type():
    return GUID()


class StrategyResult(Base):
    __tablename__ = "strategy_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(_uuid_type(), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(200), nullable=False)

    metrics: Mapped[dict] = mapped_column(_json_type(), default=dict, nullable=False)
    artifacts: Mapped[dict] = mapped_column(_json_type(), default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class PortfolioResult(Base):
    __tablename__ = "portfolio_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(_uuid_type(), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(_uuid_type(), nullable=False)

    mode: Mapped[str] = mapped_column(String(50), nullable=False)  # holdings_union | nav_blend
    metrics: Mapped[dict] = mapped_column(_json_type(), default=dict, nullable=False)
    artifacts: Mapped[dict] = mapped_column(_json_type(), default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
