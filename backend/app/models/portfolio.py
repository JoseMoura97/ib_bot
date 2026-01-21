from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base
from app.db.types import GUID


def _json_type():
    return JSON().with_variant(JSONB, "postgresql")


def _uuid_type():
    return GUID()


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = mapped_column(_uuid_type(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_cash: Mapped[float] = mapped_column(Float, default=100000.0, nullable=False)
    settings: Mapped[dict] = mapped_column(_json_type(), default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    strategies: Mapped[list["PortfolioStrategy"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )


class PortfolioStrategy(Base):
    __tablename__ = "portfolio_strategies"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "strategy_name", name="uq_portfolio_strategy"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(_uuid_type(), ForeignKey("portfolios.id", ondelete="CASCADE"))
    strategy_name: Mapped[str] = mapped_column(String(200), nullable=False)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # 0..1
    overrides: Mapped[dict] = mapped_column(_json_type(), default=dict, nullable=False)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="strategies")
