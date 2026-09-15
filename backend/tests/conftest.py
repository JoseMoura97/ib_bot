from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app

# Ensure models are registered
from app import models  # noqa: F401


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(db_session, monkeypatch):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db

    # Prevent tests from actually sending Celery tasks
    from app.worker import celery_app as celery_module

    monkeypatch.setattr(celery_module.celery_app, "send_task", lambda *args, **kwargs: None)

    # Disable rate limiting during tests
    from app.core.limiter import limiter
    limiter.enabled = False

    # Route tests use in-memory broker stubs.  Give those stubs an explicit
    # healthy observed state so they do not rely on, or wake, the deliberately
    # dormant real Gateway.  State-guard tests override this fixture directly.
    from app.api.routes import live
    from system.execution.gateway_state import GatewayState
    monkeypatch.setattr(
        live,
        "current_ib_gateway_state",
        lambda: GatewayState(True, 1_000.0, None, False, "healthy"),
    )

    with TestClient(app) as c:
        yield c

    limiter.enabled = True
    app.dependency_overrides.clear()
