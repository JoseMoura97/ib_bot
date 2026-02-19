from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas import (
    PaperAccountCreate,
    PaperAccountOut,
    PaperFundIn,
    PaperOrderIn,
    PaperOrderOut,
    PaperOrderWithTradeOut,
    PaperPositionOut,
    PaperRebalanceExecuteOut,
    PaperRebalancePreviewOut,
    PaperRebalanceRequest,
    PaperTradeOut,
)
from app.db.session import get_db
from app.models.paper import PaperAccount, PaperOrder, PaperPosition, PaperTrade
from app.models.portfolio import Portfolio, PortfolioStrategy
from app.services.paper_trading import ensure_paper_account, fetch_prices, place_market_order


router = APIRouter()


# ---- Helpers


def _account_out(a: PaperAccount) -> PaperAccountOut:
    return PaperAccountOut(
        id=int(a.id),
        name=str(a.name),
        balance=float(a.balance),
        currency=str(a.currency),
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


def _position_out(p: PaperPosition) -> PaperPositionOut:
    return PaperPositionOut(
        ticker=str(p.ticker),
        quantity=float(p.quantity),
        avg_cost=float(p.avg_cost),
        currency=str(p.currency),
        strategy=p.strategy,
        updated_at=p.updated_at,
    )


def _trade_out(t: PaperTrade) -> PaperTradeOut:
    return PaperTradeOut(
        timestamp=t.timestamp,
        ticker=str(t.ticker),
        action=str(t.action),
        quantity=float(t.quantity),
        price=float(t.price),
        value=float(t.value),
        strategy=t.strategy,
        notes=t.notes,
        order_id=t.order_id,
    )


# ---- New API (account-scoped paper trading)


@router.get("/accounts", response_model=list[PaperAccountOut])
def list_paper_accounts(db: Session = Depends(get_db)):
    rows = db.query(PaperAccount).order_by(PaperAccount.id.asc()).all()
    if not rows:
        rows = [ensure_paper_account(db, 1)]
    return [_account_out(r) for r in rows]


@router.post("/accounts", response_model=PaperAccountOut)
def create_paper_account(body: PaperAccountCreate, db: Session = Depends(get_db)):
    name = (body.name or "").strip() or "Paper Account"
    currency = (body.currency or "USD").strip().upper()
    initial_cash = float(body.initial_cash or 0.0)
    if initial_cash < 0:
        raise HTTPException(status_code=400, detail="initial_cash must be >= 0")

    acct = PaperAccount(name=name, balance=float(initial_cash), currency=currency)
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return _account_out(acct)


@router.post("/accounts/{account_id}/fund", response_model=PaperAccountOut)
def fund_paper_account(account_id: int, body: PaperFundIn, db: Session = Depends(get_db)):
    acct = ensure_paper_account(db, int(account_id))
    acct.balance = float(acct.balance) + float(body.amount)
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return _account_out(acct)


@router.get("/accounts/{account_id}/summary")
def get_paper_account_summary(account_id: int, db: Session = Depends(get_db)):
    """
    Lightweight summary used by the UI:
    - cash + currency
    - best-effort equity (cash + sum(qty * avg_cost))
    - current positions
    """
    acct = ensure_paper_account(db, int(account_id))
    rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.account_id == int(account_id), PaperPosition.quantity != 0)
        .order_by(PaperPosition.ticker.asc())
        .all()
    )
    positions = [_position_out(r) for r in rows]
    equity = float(acct.balance) + sum(float(p.quantity) * float(p.avg_cost) for p in rows)
    return {
        "cash": float(acct.balance),
        "equity": float(equity),
        "currency": str(acct.currency),
        "updated_at": acct.updated_at.isoformat(),
        "positions": [p.model_dump(mode="json") for p in positions],
    }


@router.get("/accounts/{account_id}/orders", response_model=list[PaperOrderOut])
def list_paper_orders_for_account(
    account_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    ensure_paper_account(db, int(account_id))
    rows = (
        db.query(PaperOrder)
        .filter(PaperOrder.account_id == int(account_id))
        .order_by(PaperOrder.created_at.desc())
        .limit(int(limit))
        .all()
    )
    return [
        PaperOrderOut(
            id=o.id,
            account_id=int(o.account_id),
            created_at=o.created_at,
            ticker=str(o.ticker),
            action=str(o.action),
            quantity=float(o.quantity),
            status=str(o.status),
            fill_price=float(o.fill_price),
            value=float(o.value),
        )
        for o in rows
    ]


@router.get("/accounts/{account_id}/fills", response_model=list[PaperTradeOut])
def list_paper_fills_for_account(
    account_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    ensure_paper_account(db, int(account_id))
    rows = (
        db.query(PaperTrade)
        .filter(PaperTrade.account_id == int(account_id))
        .order_by(PaperTrade.timestamp.desc())
        .limit(int(limit))
        .all()
    )
    return [_trade_out(r) for r in rows]


@router.get("/accounts/{account_id}/positions", response_model=list[PaperPositionOut])
def get_paper_positions(account_id: int, db: Session = Depends(get_db)):
    ensure_paper_account(db, int(account_id))
    rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.account_id == int(account_id), PaperPosition.quantity != 0)
        .order_by(PaperPosition.ticker.asc())
        .all()
    )
    return [_position_out(r) for r in rows]


@router.get("/accounts/{account_id}/trades", response_model=list[PaperTradeOut])
def get_paper_trades_for_account(
    account_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    ensure_paper_account(db, int(account_id))
    rows = (
        db.query(PaperTrade)
        .filter(PaperTrade.account_id == int(account_id))
        .order_by(PaperTrade.timestamp.desc())
        .limit(int(limit))
        .all()
    )
    return [_trade_out(r) for r in rows]


@router.post("/accounts/{account_id}/orders", response_model=PaperOrderWithTradeOut)
def place_paper_order(account_id: int, body: PaperOrderIn, db: Session = Depends(get_db)):
    try:
        order, trade, acct, pos = place_market_order(
            db,
            account_id=int(account_id),
            ticker=body.ticker,
            side=body.side,
            quantity=float(body.quantity),
            price=body.price,
            notes=body.notes,
            strategy=body.strategy,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    db.commit()
    db.refresh(order)
    db.refresh(trade)
    db.refresh(acct)
    db.refresh(pos)

    return PaperOrderWithTradeOut(
        order=PaperOrderOut(
            id=order.id,
            account_id=int(order.account_id),
            created_at=order.created_at,
            ticker=str(order.ticker),
            action=str(order.action),
            quantity=float(order.quantity),
            status=str(order.status),
            fill_price=float(order.fill_price),
            value=float(order.value),
        ),
        trade=_trade_out(trade),
        account=_account_out(acct),
        position=_position_out(pos),
    )


@router.post("/rebalance/preview", response_model=PaperRebalancePreviewOut)
def paper_rebalance_preview(body: PaperRebalanceRequest, db: Session = Depends(get_db)):
    # Validate portfolio + fetch strategy config
    p = db.query(Portfolio).filter(Portfolio.id == str(body.portfolio_id)).one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    acct = ensure_paper_account(db, int(body.account_id))

    strategies = (
        db.query(PortfolioStrategy)
        .filter(PortfolioStrategy.portfolio_id == p.id, PortfolioStrategy.enabled.is_(True))
        .all()
    )
    if not strategies:
        raise HTTPException(status_code=400, detail="Portfolio has no enabled strategies")

    # Build combined target weights using latest rebalance events per strategy.
    from app.core.config import settings

    end = datetime.utcnow()

    # If QUIVER_API_KEY is not configured, fall back to a deterministic, no-secrets
    # rebalance target so the paper-trading workflow still works end-to-end.
    # This keeps "docker compose up" usable out-of-the-box.
    if not settings.quiver_api_key:
        combined: dict[str, float] = {"SPY": 1.0}
        weight_sum = 1.0
    else:
        from rebalancing_backtest_engine import RebalancingBacktestEngine  # repo root import

        bt = RebalancingBacktestEngine(
            quiver_api_key=settings.quiver_api_key,
            initial_capital=float(body.allocation_amount),
            transaction_cost_bps=0.0,
            price_source=settings.price_source,
        )

        start = end - timedelta(days=365)

        combined = {}
        weight_sum = 0.0
        for s in strategies:
            w = float(s.weight or 0.0)
            if w <= 0:
                continue
            evs = bt._generate_rebalance_events(
                strategy_name=s.strategy_name, start=start, end=end, lookback_days_override=None
            )
            if not evs:
                continue
            last = evs[-1]
            wmap = bt._clean_weight_map(last.weights or {})
            for tkr, tw in (wmap or {}).items():
                combined[tkr] = combined.get(tkr, 0.0) + (w * float(tw))
            weight_sum += w

    if not combined:
        raise HTTPException(status_code=400, detail="No target tickers available for rebalance")

    # Normalize to long-only weights for paper trading.
    combined = {t: float(w) for t, w in combined.items() if float(w) > 0}
    ssum = sum(combined.values())
    if ssum <= 0:
        raise HTTPException(status_code=400, detail="No positive target weights available for rebalance")
    combined = {t: float(w) / ssum for t, w in combined.items()}

    quotes = fetch_prices(combined.keys())

    # Current quantities for delta calc
    current_positions = {
        r.ticker: float(r.quantity)
        for r in db.query(PaperPosition).filter(PaperPosition.account_id == int(body.account_id)).all()
    }

    legs = []
    total_target_value = 0.0
    for t, w in sorted(combined.items(), key=lambda kv: kv[0]):
        q = quotes.get(t)
        if q is None or q.price <= 0:
            continue
        target_value = float(body.allocation_amount) * float(w)
        target_qty = float(int(target_value / float(q.price)))  # integer shares
        cur_qty = float(current_positions.get(t, 0.0))
        delta = float(target_qty - cur_qty)
        if abs(delta) < 1e-9:
            continue
        side = "BUY" if delta > 0 else "SELL"
        legs.append(
            {
                "ticker": t,
                "target_weight": float(w),
                "price": float(q.price),
                "target_value": float(target_value),
                "target_quantity": float(target_qty),
                "current_quantity": float(cur_qty),
                "delta_quantity": float(delta),
                "side": side,
            }
        )
        total_target_value += float(abs(delta) * float(q.price) if delta > 0 else 0.0)

    estimated_remaining = float(acct.balance) - total_target_value

    return PaperRebalancePreviewOut(
        as_of=end,
        portfolio_id=body.portfolio_id,
        account_id=int(body.account_id),
        allocation_amount=float(body.allocation_amount),
        estimated_cash_remaining=float(estimated_remaining),
        legs=legs,  # pydantic will coerce dicts into model
    )


@router.post("/rebalance/execute", response_model=PaperRebalanceExecuteOut)
def paper_rebalance_execute(body: PaperRebalanceRequest, db: Session = Depends(get_db)):
    preview = paper_rebalance_preview(body, db)  # reuse logic (includes ensure_paper_account)
    acct = db.query(PaperAccount).filter(PaperAccount.id == int(body.account_id)).one()

    # Execute SELLs first (raise cash), then BUYs.
    sells = [l for l in preview.legs if l.side == "SELL"]
    buys = [l for l in preview.legs if l.side == "BUY"]
    orders: list[PaperOrder] = []
    trades: list[PaperTrade] = []

    try:
        for leg in sells + buys:
            o, tr, _, _ = place_market_order(
                db,
                account_id=int(body.account_id),
                ticker=leg.ticker,
                side=leg.side,
                quantity=float(abs(leg.delta_quantity)),
                price=float(leg.price),
                notes=f"rebalance portfolio {body.portfolio_id}",
                strategy=None,
            )
            orders.append(o)
            trades.append(tr)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e

    db.commit()
    db.refresh(acct)

    return PaperRebalanceExecuteOut(
        as_of=preview.as_of,
        portfolio_id=body.portfolio_id,
        account_id=int(body.account_id),
        orders=[
            PaperOrderOut(
                id=o.id,
                account_id=int(o.account_id),
                created_at=o.created_at,
                ticker=str(o.ticker),
                action=str(o.action),
                quantity=float(o.quantity),
                status=str(o.status),
                fill_price=float(o.fill_price),
                value=float(o.value),
            )
            for o in orders
        ],
        trades=[_trade_out(t) for t in trades],
        account=_account_out(acct),
    )


# ---- P&L / Snapshot endpoints


@router.get("/accounts/{account_id}/snapshots")
def get_paper_snapshots(
    account_id: int,
    limit: int = Query(default=365, ge=1, le=3650),
    db: Session = Depends(get_db),
):
    """Return time-series of equity/cash snapshots for a paper account."""
    from app.models.paper import PaperSnapshot

    ensure_paper_account(db, int(account_id))
    rows = (
        db.query(PaperSnapshot)
        .filter(PaperSnapshot.account_id == int(account_id))
        .order_by(PaperSnapshot.timestamp.asc())
        .limit(int(limit))
        .all()
    )
    return [
        {
            "timestamp": r.timestamp.isoformat(),
            "cash": float(r.cash),
            "equity": float(r.equity),
            "portfolio_id": r.portfolio_id,
        }
        for r in rows
    ]


@router.get("/accounts/{account_id}/pnl")
def get_paper_pnl(
    account_id: int,
    db: Session = Depends(get_db),
):
    """Compute daily and cumulative P&L from snapshots."""
    from app.models.paper import PaperSnapshot

    ensure_paper_account(db, int(account_id))
    rows = (
        db.query(PaperSnapshot)
        .filter(PaperSnapshot.account_id == int(account_id))
        .order_by(PaperSnapshot.timestamp.asc())
        .all()
    )
    if not rows:
        return {"daily": [], "summary": {"total_return": 0, "total_pnl": 0, "days": 0}}

    daily = []
    first_equity = float(rows[0].equity)
    prev_equity = first_equity
    for r in rows:
        eq = float(r.equity)
        daily_pnl = eq - prev_equity
        daily.append({
            "date": r.timestamp.strftime("%Y-%m-%d"),
            "equity": eq,
            "cash": float(r.cash),
            "daily_pnl": round(daily_pnl, 2),
            "cumulative_pnl": round(eq - first_equity, 2),
        })
        prev_equity = eq

    last_equity = float(rows[-1].equity)
    total_pnl = last_equity - first_equity
    total_return = total_pnl / first_equity if first_equity > 0 else 0
    max_equity = first_equity
    max_dd = 0.0
    for r in rows:
        eq = float(r.equity)
        if eq > max_equity:
            max_equity = eq
        dd = (eq - max_equity) / max_equity if max_equity > 0 else 0
        if dd < max_dd:
            max_dd = dd

    return {
        "daily": daily,
        "summary": {
            "total_return": round(total_return, 6),
            "total_pnl": round(total_pnl, 2),
            "max_drawdown": round(max_dd, 6),
            "days": len(rows),
            "first_equity": round(first_equity, 2),
            "last_equity": round(last_equity, 2),
        },
    }


@router.get("/accounts/{account_id}/rebalance-logs")
def get_paper_rebalance_logs(
    account_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Return rebalance history for a paper account."""
    from app.models.paper import PaperRebalanceLog

    ensure_paper_account(db, int(account_id))
    rows = (
        db.query(PaperRebalanceLog)
        .filter(PaperRebalanceLog.account_id == int(account_id))
        .order_by(PaperRebalanceLog.timestamp.desc())
        .limit(int(limit))
        .all()
    )
    return [
        {
            "id": r.id,
            "timestamp": r.timestamp.isoformat(),
            "portfolio_id": r.portfolio_id,
            "status": r.status,
            "n_orders": r.n_orders,
            "details": r.details or {},
        }
        for r in rows
    ]


# ---- Backward-compatible legacy endpoints

@router.get("/portfolio")
def get_paper_portfolio(db: Session = Depends(get_db)):
    cash = ensure_paper_account(db, 1)
    positions = db.query(PaperPosition).filter(PaperPosition.account_id == 1, PaperPosition.quantity != 0).all()
    return {
        "cash": {"balance": cash.balance, "currency": cash.currency, "updated_at": cash.updated_at.isoformat()},
        "positions": [
            {
                "ticker": p.ticker,
                "quantity": p.quantity,
                "avg_cost": p.avg_cost,
                "currency": p.currency,
                "strategy": p.strategy,
                "updated_at": p.updated_at.isoformat(),
            }
            for p in positions
        ],
    }


@router.get("/trades")
def get_paper_trades(limit: int = 50, db: Session = Depends(get_db)):
    ensure_paper_account(db, 1)
    rows = (
        db.query(PaperTrade)
        .filter(PaperTrade.account_id == 1)
        .order_by(PaperTrade.timestamp.desc())
        .limit(int(limit))
        .all()
    )
    return [
        {
            "timestamp": r.timestamp.isoformat(),
            "ticker": r.ticker,
            "action": r.action,
            "quantity": r.quantity,
            "price": r.price,
            "value": r.value,
            "strategy": r.strategy,
            "notes": r.notes,
        }
        for r in rows
    ]
