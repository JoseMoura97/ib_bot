from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import CreatePortfolioBacktestRun, CreateValidationRun, RunOut
from app.db.session import get_db
from app.models.portfolio import Portfolio, PortfolioStrategy
from app.models.result import PortfolioResult, StrategyResult
from app.models.run import Run
from app.worker.celery_app import celery_app


router = APIRouter()


@router.get("", response_model=list[RunOut])
def list_runs(limit: int = 50, db: Session = Depends(get_db)):
    rows = db.query(Run).order_by(Run.created_at.desc()).limit(int(limit)).all()
    return [
        RunOut(
            id=r.id,
            type=r.type,
            status=r.status,
            params=r.params or {},
            progress=r.progress or {},
            created_at=r.created_at,
            started_at=r.started_at,
            finished_at=r.finished_at,
            error=r.error,
        )
        for r in rows
    ]


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: UUID, db: Session = Depends(get_db)):
    r = db.query(Run).filter(Run.id == run_id).one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunOut(
        id=r.id,
        type=r.type,
        status=r.status,
        params=r.params or {},
        progress=r.progress or {},
        created_at=r.created_at,
        started_at=r.started_at,
        finished_at=r.finished_at,
        error=r.error,
    )


@router.get("/{run_id}/results")
def get_run_results(run_id: UUID, db: Session = Depends(get_db)):
    r = db.query(Run).filter(Run.id == run_id).one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="Run not found")

    portfolios = db.query(PortfolioResult).filter(PortfolioResult.run_id == run_id).all()
    strategies = db.query(StrategyResult).filter(StrategyResult.run_id == run_id).all()

    return {
        "run": {"id": str(r.id), "type": r.type, "status": r.status},
        "portfolio_results": [
            {
                "portfolio_id": str(pr.portfolio_id),
                "mode": pr.mode,
                "metrics": pr.metrics or {},
                "artifacts": pr.artifacts or {},
            }
            for pr in portfolios
        ],
        "strategy_results": [
            {"strategy_name": sr.strategy_name, "metrics": sr.metrics or {}, "artifacts": sr.artifacts or {}}
            for sr in strategies
        ],
    }


@router.post("/portfolio-backtest", response_model=RunOut)
def create_portfolio_backtest(body: CreatePortfolioBacktestRun, db: Session = Depends(get_db)):
    p = db.query(Portfolio).filter(Portfolio.id == body.portfolio_id).one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    ps = (
        db.query(PortfolioStrategy)
        .filter(PortfolioStrategy.portfolio_id == p.id, PortfolioStrategy.enabled.is_(True))
        .all()
    )
    if not ps:
        raise HTTPException(status_code=400, detail="Portfolio has no enabled strategies")

    # Ensure JSON-serializable (UUID -> str)
    params = body.model_dump(mode="json")
    params["strategies"] = [{"name": s.strategy_name, "weight": float(s.weight)} for s in ps]

    r = Run(type="portfolio_backtest", status="PENDING", params=params, progress={})
    db.add(r)
    db.commit()
    db.refresh(r)

    # Enqueue background job
    celery_app.send_task("portfolio_backtest_task", args=[str(r.id)])

    return RunOut(
        id=r.id,
        type=r.type,
        status=r.status,
        params=r.params or {},
        progress=r.progress or {},
        created_at=r.created_at,
        started_at=r.started_at,
        finished_at=r.finished_at,
        error=r.error,
    )


@router.post("/validation", response_model=RunOut)
def create_validation_run(body: CreateValidationRun, db: Session = Depends(get_db)):
    params = body.model_dump(mode="json")
    r = Run(type="validation", status="PENDING", params=params, progress={})
    db.add(r)
    db.commit()
    db.refresh(r)

    celery_app.send_task("validation_task", args=[str(r.id)])

    return RunOut(
        id=r.id,
        type=r.type,
        status=r.status,
        params=r.params or {},
        progress=r.progress or {},
        created_at=r.created_at,
        started_at=r.started_at,
        finished_at=r.finished_at,
        error=r.error,
    )
