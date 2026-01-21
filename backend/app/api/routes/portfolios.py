from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import (
    PortfolioCreate,
    PortfolioOut,
    PortfolioPatch,
    PortfolioStrategyIn,
    PortfolioWithStrategies,
)
from app.db.session import get_db
from app.models.portfolio import Portfolio, PortfolioStrategy


router = APIRouter()


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
