from __future__ import annotations

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings
from app.db.init_db import create_all


app = FastAPI(title="IB Bot API")
app.include_router(api_router)


@app.on_event("startup")
def _startup() -> None:
    # For local/dev: allow auto-create. In Docker/VM, you should run Alembic migrations.
    if settings.database_url.startswith("sqlite"):
        create_all()
