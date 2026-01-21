from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base
from app.db.types import GUID


def _json_type():
    return JSON().with_variant(JSONB, "postgresql")


def _uuid_type():
    return GUID()


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(_uuid_type(), primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # validation/backtest/portfolio_backtest/paper/live
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")  # PENDING/RUNNING/SUCCESS/ERROR

    params: Mapped[dict] = mapped_column(_json_type(), default=dict, nullable=False)
    progress: Mapped[dict] = mapped_column(_json_type(), default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
