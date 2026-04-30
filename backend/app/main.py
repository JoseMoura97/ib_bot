from __future__ import annotations

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.limiter import limiter
from app.db.init_db import create_all
from app.services.ib_worker import stop_ib_worker

app = FastAPI(title="IB Bot API")
app.state.limiter = limiter


# ---------------------------------------------------------------------------
# Rate-limit error handler
# ---------------------------------------------------------------------------

@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> Response:
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})


# ---------------------------------------------------------------------------
# API key authentication middleware
# ---------------------------------------------------------------------------

_AUTH_EXEMPT_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if settings.api_key:
            path = request.url.path
            if not any(path.startswith(p) for p in _AUTH_EXEMPT_PREFIXES):
                provided = request.headers.get("x-api-key") or request.query_params.get("api_key")
                if provided != settings.api_key:
                    return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
        return await call_next(request)


app.add_middleware(AuthMiddleware)


# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------

_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


app.include_router(api_router)


@app.on_event("startup")
def _startup() -> None:
    if settings.database_url.startswith("sqlite"):
        create_all()


@app.on_event("shutdown")
def _shutdown() -> None:
    stop_ib_worker()
