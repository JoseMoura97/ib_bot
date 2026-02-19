from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import (
    OptimizeCompareRequest,
    OptimizeRequest,
    PortfolioCreate,
    PortfolioOut,
    PortfolioPatch,
    PortfolioStrategyIn,
    PortfolioWithStrategies,
)
from app.db.session import get_db
from app.models.portfolio import Portfolio, PortfolioStrategy
from app.services.portfolio_math import (
    compare_all_methods,
    optimize_portfolio,
    records_to_series,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _load_strategy_curves(strategy_names: list[str]) -> Dict[str, pd.Series]:
    """Load equity curves from .cache/plot_data.json for given strategy names."""
    path = Path(os.getenv("PLOT_DATA_PATH", "/app/.cache/plot_data.json"))
    if not path.exists():
        for fallback in [Path(".cache/plot_data.json"), Path("../.cache/plot_data.json")]:
            if fallback.exists():
                path = fallback
                break
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Failed to read plot_data.json for optimizer")
        return {}

    strategies_data = payload.get("strategies", {})
    curves: Dict[str, pd.Series] = {}
    for name in strategy_names:
        entry = strategies_data.get(name)
        if not entry:
            continue
        equity = entry.get("equity_curve", [])
        if not equity:
            continue
        s = records_to_series(equity)
        if not s.empty:
            curves[name] = s
    return curves


@router.get("", response_model=list[PortfolioOut])
def list_portfolios(db: Session = Depends(get_db)):
    rows = db.query(Portfolio).order_by(Portfolio.created_at.desc()).all()
    return [
        PortfolioOut(
            id=r.id,
            name=r.name,
            description=r.description,
            default_cash=r.default_cash,
            settings=r.settings or {},
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.post("", response_model=PortfolioOut)
def create_portfolio(body: PortfolioCreate, db: Session = Depends(get_db)):
    p = Portfolio(
        name=body.name,
        description=body.description,
        default_cash=float(body.default_cash),
        settings=body.settings or {},
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return PortfolioOut(
        id=p.id,
        name=p.name,
        description=p.description,
        default_cash=p.default_cash,
        settings=p.settings or {},
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.patch("/{portfolio_id}", response_model=PortfolioOut)
def patch_portfolio(portfolio_id: str, body: PortfolioPatch, db: Session = Depends(get_db)):
    p = db.query(Portfolio).filter(Portfolio.id == portfolio_id).one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    if body.name is not None:
        p.name = body.name
    if body.description is not None:
        p.description = body.description
    if body.default_cash is not None:
        p.default_cash = float(body.default_cash)
    if body.settings is not None:
        p.settings = body.settings or {}

    db.commit()
    db.refresh(p)
    return PortfolioOut(
        id=p.id,
        name=p.name,
        description=p.description,
        default_cash=p.default_cash,
        settings=p.settings or {},
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get("/{portfolio_id}", response_model=PortfolioWithStrategies)
def get_portfolio(portfolio_id: str, db: Session = Depends(get_db)):
    p = db.query(Portfolio).filter(Portfolio.id == portfolio_id).one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    strategies = db.query(PortfolioStrategy).filter(PortfolioStrategy.portfolio_id == p.id).all()
    return PortfolioWithStrategies(
        id=p.id,
        name=p.name,
        description=p.description,
        default_cash=p.default_cash,
        settings=p.settings or {},
        created_at=p.created_at,
        updated_at=p.updated_at,
        strategies=[
            PortfolioStrategyIn(
                strategy_name=s.strategy_name,
                enabled=s.enabled,
                weight=float(s.weight),
                overrides=s.overrides or {},
            )
            for s in strategies
        ],
    )


@router.put("/{portfolio_id}/strategies", response_model=PortfolioWithStrategies)
def set_portfolio_strategies(
    portfolio_id: str, body: list[PortfolioStrategyIn], db: Session = Depends(get_db)
):
    p = db.query(Portfolio).filter(Portfolio.id == portfolio_id).one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    # Validate weights before applying changes.
    enabled_rows = [s for s in body if bool(s.enabled)]
    for s in body:
        w = float(s.weight)
        if w < 0 or w > 1:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid weight for {s.strategy_name}: must be between 0 and 1",
            )
    if enabled_rows:
        total_weight = sum(float(s.weight) for s in enabled_rows)
        if total_weight <= 0:
            raise HTTPException(status_code=400, detail="Enabled strategies must have positive weights")
        if abs(total_weight - 1.0) > 0.01:
            raise HTTPException(
                status_code=400,
                detail=f"Enabled strategy weights must sum to 1.0 (got {total_weight:.4f})",
            )

    # Replace strategy list atomically.
    db.query(PortfolioStrategy).filter(PortfolioStrategy.portfolio_id == p.id).delete()
    for s in body:
        db.add(
            PortfolioStrategy(
                portfolio_id=p.id,
                strategy_name=s.strategy_name,
                enabled=bool(s.enabled),
                weight=float(s.weight),
                overrides=s.overrides or {},
            )
        )
    db.commit()

    strategies = db.query(PortfolioStrategy).filter(PortfolioStrategy.portfolio_id == p.id).all()
    return PortfolioWithStrategies(
        id=p.id,
        name=p.name,
        description=p.description,
        default_cash=p.default_cash,
        settings=p.settings or {},
        created_at=p.created_at,
        updated_at=p.updated_at,
        strategies=[
            PortfolioStrategyIn(
                strategy_name=s.strategy_name,
                enabled=s.enabled,
                weight=float(s.weight),
                overrides=s.overrides or {},
            )
            for s in strategies
        ],
    )


# ---------------------------------------------------------------------------
# Portfolio weight optimization
# ---------------------------------------------------------------------------


@router.post("/{portfolio_id}/optimize")
def optimize_weights(portfolio_id: str, body: OptimizeRequest, db: Session = Depends(get_db)):
    """Suggest optimized weights for a portfolio's enabled strategies."""
    p = db.query(Portfolio).filter(Portfolio.id == portfolio_id).one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    strats = db.query(PortfolioStrategy).filter(
        PortfolioStrategy.portfolio_id == p.id,
        PortfolioStrategy.enabled == True,
    ).all()
    if not strats:
        raise HTTPException(status_code=400, detail="Portfolio has no enabled strategies")

    strategy_names = [s.strategy_name for s in strats]
    curves = _load_strategy_curves(strategy_names)
    if not curves:
        raise HTTPException(
            status_code=400,
            detail="No cached equity curves found for portfolio strategies. Run backtests or update plot data first.",
        )

    missing = [n for n in strategy_names if n not in curves]
    result = optimize_portfolio(
        curves, body.method,
        max_weight=body.max_weight, min_weight=body.min_weight,
        risk_free_rate=body.risk_free_rate,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    result["missing_strategies"] = missing
    result["available_strategies"] = list(curves.keys())
    return result


@router.post("/{portfolio_id}/optimize/compare")
def compare_optimization_methods(
    portfolio_id: str, body: OptimizeCompareRequest, db: Session = Depends(get_db)
):
    """Run all 4 optimization methods side-by-side for comparison."""
    p = db.query(Portfolio).filter(Portfolio.id == portfolio_id).one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    strats = db.query(PortfolioStrategy).filter(
        PortfolioStrategy.portfolio_id == p.id,
        PortfolioStrategy.enabled == True,
    ).all()
    if not strats:
        raise HTTPException(status_code=400, detail="Portfolio has no enabled strategies")

    strategy_names = [s.strategy_name for s in strats]
    curves = _load_strategy_curves(strategy_names)
    if not curves:
        raise HTTPException(
            status_code=400,
            detail="No cached equity curves found for portfolio strategies.",
        )

    missing = [n for n in strategy_names if n not in curves]
    results = compare_all_methods(
        curves,
        max_weight=body.max_weight, min_weight=body.min_weight,
        risk_free_rate=body.risk_free_rate,
    )
    return {
        "available_strategies": list(curves.keys()),
        "missing_strategies": missing,
        "methods": results,
    }
