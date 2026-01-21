from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import engine

# Ensure models are imported so metadata is populated.
from app import models  # noqa: F401


def create_all() -> None:
    Base.metadata.create_all(bind=engine)


def drop_all() -> None:
    Base.metadata.drop_all(bind=engine)
