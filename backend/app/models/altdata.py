from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base


def _json_type():
    return JSON().with_variant(JSONB, "postgresql")


class AltDataSnapshot(Base):
    """Point-in-time vintage of an alternative-data source, captured daily.

    This is the only *compounding, un-replicable* asset: once we store what a
    source looked like as-of a given date, a latecomer cannot reconstruct it.
    `payload` holds the source's records; on an unchanged day we store
    metadata-only (payload NULL, same content_hash) to avoid bloat.
    """

    __tablename__ = "altdata_snapshots"
    __table_args__ = (UniqueConstraint("source", "as_of_date", name="uq_altdata_source_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    n_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    payload: Mapped[dict | None] = mapped_column(_json_type(), nullable=True)
