from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import GUID


class PortfolioAllocation(Base):
    """
    Simple allocation ledger.
    - account_id: external identifier (paper account id as string, or IB account id)
    - mode: "paper" or "live"
    """

    __tablename__ = "portfolio_allocations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="paper")
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)

    amount: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

