from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base
from app.db.types import GUID


def _json_type():
    return JSON().with_variant(JSONB, "postgresql")


class IBOrder(Base):
    __tablename__ = "ib_orders"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    account: Mapped[str | None] = mapped_column(String(64), nullable=True)

    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(8), nullable=False)  # BUY/SELL
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    order_type: Mapped[str] = mapped_column(String(32), nullable=False, default="MKT")

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="SUBMITTED")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    raw: Mapped[dict] = mapped_column(_json_type(), default=dict, nullable=False)


class IBTrade(Base):
    __tablename__ = "ib_trades"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    raw: Mapped[dict] = mapped_column(_json_type(), default=dict, nullable=False)
