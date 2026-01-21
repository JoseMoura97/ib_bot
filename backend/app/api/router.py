from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import allocations, dashboard, health, ib, live, metrics, paper, plot_data, portfolios, runs, strategies


api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(strategies.router, prefix="/strategies", tags=["strategies"])
api_router.include_router(plot_data.router, prefix="/plot-data", tags=["plot-data"])
api_router.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
api_router.include_router(portfolios.router, prefix="/portfolios", tags=["portfolios"])
api_router.include_router(runs.router, prefix="/runs", tags=["runs"])
api_router.include_router(paper.router, prefix="/paper", tags=["paper"])
api_router.include_router(allocations.router, prefix="/allocations", tags=["allocations"])
api_router.include_router(ib.router, prefix="/ib", tags=["ib"])
api_router.include_router(live.router, prefix="/live", tags=["live"])
