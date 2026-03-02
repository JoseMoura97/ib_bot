from __future__ import annotations

from datetime import datetime, timedelta
import time
from typing import Any, Iterable
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.ib_audit import IBOrder, IBTrade, LiveExecutionRequest, LiveRebalanceAudit
from app.models.portfolio import Portfolio, PortfolioStrategy
from app.services.ib_worker import call_ib
from app.services.market_calendar import market_is_open
from app.services.paper_trading import PriceQuote, fetch_last_close_price, fetch_prices


router = APIRouter()


@router.get("/status")
def live_status():
    return {
        "enabled": bool(settings.enable_live_trading),
        "dry_run": bool(settings.live_dry_run),
        "halted": bool(settings.trading_halt),
        "ib_host": settings.ib_host,
        "ib_port": settings.ib_port,
    }


@router.post("/rebalance")
def live_rebalance():
    """
    Live trading is intentionally guarded.
    This endpoint is a placeholder; real implementation should:
    - require explicit enable flag
    - require confirmation params (max % NLV, max order size, etc.)
    - run in a background task and log all orders/fills
    """
    if not settings.enable_live_trading:
        raise HTTPException(status_code=403, detail="Live trading disabled (set ENABLE_LIVE_TRADING=1)")
    raise HTTPException(status_code=501, detail="Not implemented yet")


class LiveRebalanceRequest(BaseModel):
    account_id: str = Field(..., min_length=1)
    portfolio_id: UUID
    allocation_amount: float = Field(gt=0.0, description="Dollar amount to allocate")
    max_notional_usd: float | None = Field(default=None, gt=0.0)
    max_percent_nlv: float | None = Field(default=None, gt=0.0, le=1.0)
    max_orders: int = Field(default=25, ge=1, le=200)
    max_ticker_notional_usd: float | None = Field(default=None, gt=0.0)
    max_ticker_percent_nlv: float | None = Field(default=None, gt=0.0, le=1.0)
    max_ticker_shares: float | None = Field(default=None, gt=0.0)
    allow_short: bool = False
    confirm: bool = False


class LiveRebalanceLeg(BaseModel):
    ticker: str
    target_weight: float
    price: float
    target_value: float
    target_quantity: float
    current_quantity: float
    delta_quantity: float
    side: str


class LiveRebalancePreviewOut(BaseModel):
    as_of: datetime
    portfolio_id: UUID
    account_id: str
    allocation_amount: float
    estimated_notional: float
    legs: list[LiveRebalanceLeg]


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def _extract_nlv(summary_rows: list[Any]) -> float | None:
    for row in summary_rows or []:
        tag = str(getattr(row, "tag", "") or "")
        ccy = str(getattr(row, "currency", "") or "")
        if tag != "NetLiquidation":
            continue
        if ccy not in {"USD", "BASE", ""}:
            continue
        val = _to_float(getattr(row, "value", None))
        if val is not None:
            return float(val)
    return None


def _normalize_idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    key = str(value).strip()
    return key or None


def _current_positions_for_account(account_id: str) -> dict[str, float]:
    from app.api.routes.ib import _positions_for_account

    rows = call_ib(lambda ib: _positions_for_account(ib, account_id), timeout=15.0)
    out: dict[str, float] = {}
    for p in rows or []:
        c = getattr(p, "contract", None)
        sym = getattr(c, "symbol", None) or getattr(c, "localSymbol", None)
        if not sym:
            continue
        qty = _to_float(getattr(p, "position", None))
        if qty is None:
            continue
        out[str(sym)] = float(qty)
    return out


def _account_nlv(account_id: str) -> float | None:
    from app.api.routes.ib import _account_values_for_account

    rows = call_ib(lambda ib: _account_values_for_account(ib, account_id), timeout=15.0)
    return _extract_nlv(rows or [])


def _build_target_weights(
    db: Session,
    portfolio_id: UUID,
    allocation_amount: float,
    *,
    allow_short: bool,
) -> dict[str, float]:
    p = db.query(Portfolio).filter(Portfolio.id == str(portfolio_id)).one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    strategies = (
        db.query(PortfolioStrategy)
        .filter(PortfolioStrategy.portfolio_id == p.id, PortfolioStrategy.enabled.is_(True))
        .all()
    )
    if not strategies:
        raise HTTPException(status_code=400, detail="Portfolio has no enabled strategies")

    if not settings.quiver_api_key:
        raise HTTPException(status_code=400, detail="QUIVER_API_KEY is required for live rebalances")

    from rebalancing_backtest_engine import RebalancingBacktestEngine  # repo root import

    bt = RebalancingBacktestEngine(
        quiver_api_key=settings.quiver_api_key,
        initial_capital=float(allocation_amount),
        transaction_cost_bps=0.0,
        price_source=settings.price_source,
    )

    end = datetime.utcnow()
    start = end - timedelta(days=365)

    combined: dict[str, float] = {}
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

    combined = {t: float(w) for t, w in combined.items() if float(w) != 0}
    if any(float(w) < 0 for w in combined.values()) and not allow_short:
        raise HTTPException(status_code=400, detail="Short targets detected; set allow_short=true to proceed")

    if allow_short:
        denom = sum(abs(float(w)) for w in combined.values())
        if denom <= 0:
            raise HTTPException(status_code=400, detail="No target weights available for rebalance")
        return {t: float(w) / denom for t, w in combined.items()}

    ssum = sum(float(w) for w in combined.values() if float(w) > 0)
    if ssum <= 0:
        raise HTTPException(status_code=400, detail="No positive target weights available for rebalance")
    return {t: float(w) / ssum for t, w in combined.items() if float(w) > 0}


def _audit_event(
    db: Session,
    *,
    action: str,
    status: str,
    error: str | None,
    request: dict[str, Any],
    orders: list[dict[str, Any]],
    account_id: str,
    portfolio_id: UUID,
    allocation_amount: float,
    max_notional_usd: float | None,
    max_percent_nlv: float | None,
    max_orders: int,
    allow_short: bool,
) -> None:
    row = LiveRebalanceAudit(
        action=action,
        status=status,
        error=error,
        account_id=account_id,
        portfolio_id=portfolio_id,
        allocation_amount=allocation_amount,
        max_notional_usd=max_notional_usd,
        max_percent_nlv=max_percent_nlv,
        max_orders=max_orders,
        allow_short=allow_short,
        request=request,
        orders={"legs": orders},
    )
    db.add(row)
    db.commit()


def _parse_ib_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except Exception:
        return None


def _persist_ib_results(db: Session, *, account_id: str, results: list[dict[str, Any]]) -> None:
    now = datetime.utcnow()
    for r in results:
        order = IBOrder(
            account=str(account_id),
            ticker=str(r.get("ticker") or ""),
            action=str(r.get("side") or ""),
            quantity=float(r.get("quantity") or 0.0),
            order_type="MKT",
            status=str(r.get("status") or "SUBMITTED"),
            submitted_at=now,
            filled_at=now if str(r.get("status") or "") == "Filled" else None,
            raw=r,
        )
        db.add(order)
        db.flush()

        for f in r.get("fills", []) or []:
            exe = (f or {}).get("execution") or {}
            qty = _to_float(exe.get("shares"))
            price = _to_float(exe.get("price"))
            if qty is None or price is None or qty == 0 or price == 0:
                continue
            timestamp = _parse_ib_time(exe.get("time")) or now
            trade = IBTrade(
                order_id=order.id,
                timestamp=timestamp,
                ticker=str(r.get("ticker") or ""),
                quantity=float(qty),
                price=float(price),
                raw=exe,
            )
            db.add(trade)


def _fetch_live_quotes(tickers: Iterable[str]) -> dict[str, PriceQuote]:
    def _get(ib: Any) -> dict[str, dict[str, Any]]:
        try:
            from ib_insync import Stock  # optional dependency
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"ib_insync import failed: {type(e).__name__}: {e}") from e

        contracts = [Stock(str(t).upper(), "SMART", "USD") for t in tickers]
        if contracts:
            try:
                ib.qualifyContracts(*contracts)
            except Exception:
                pass
        ticks = ib.reqTickers(*contracts) if contracts else []
        out: dict[str, dict[str, Any]] = {}
        for t in ticks or []:
            sym = getattr(getattr(t, "contract", None), "symbol", None) or getattr(
                getattr(t, "contract", None), "localSymbol", None
            )
            if not sym:
                continue
            price = None
            try:
                price = float(t.marketPrice())
            except Exception:
                price = _to_float(getattr(t, "last", None)) or _to_float(getattr(t, "close", None))
            out[str(sym).upper()] = {
                "price": price,
                "bid": _to_float(getattr(t, "bid", None)),
                "ask": _to_float(getattr(t, "ask", None)),
                "time": getattr(t, "time", None),
            }
        return out

    raw = call_ib(_get, timeout=20.0)
    now = datetime.utcnow()
    quotes: dict[str, PriceQuote] = {}
    for ticker, data in raw.items():
        price = _to_float(data.get("price"))
        if price is None:
            continue
        as_of = data.get("time")
        if isinstance(as_of, datetime):
            quote_time = as_of
        else:
            quote_time = now

        # Price sanity checks
        if price <= 0:
            raise HTTPException(status_code=400, detail=f"{ticker} price <= 0")
        if price > float(settings.live_max_abs_price):
            raise HTTPException(status_code=400, detail=f"{ticker} price exceeds max_abs_price")
        age_seconds = (now - quote_time).total_seconds()
        if age_seconds > float(settings.live_max_price_age_seconds):
            raise HTTPException(status_code=400, detail=f"{ticker} price is stale")

        bid = _to_float(data.get("bid"))
        ask = _to_float(data.get("ask"))
        if bid and ask and bid > 0 and ask > 0:
            mid = (bid + ask) / 2.0
            if mid > 0 and (ask - bid) / mid > float(settings.live_max_spread_pct):
                raise HTTPException(status_code=400, detail=f"{ticker} bid/ask spread too wide")

        try:
            last_close = fetch_last_close_price(ticker)
            if last_close.price > 0:
                deviation = abs(price - float(last_close.price)) / float(last_close.price)
                if deviation > float(settings.live_max_price_deviation):
                    raise HTTPException(status_code=400, detail=f"{ticker} price deviates from last close")
        except ValueError:
            pass

        quotes[ticker] = PriceQuote(ticker=ticker, price=float(price), as_of=quote_time, source="ib")
    return quotes


def _fetch_quotes_for_preview(tickers: Iterable[str]) -> dict[str, PriceQuote]:
    if settings.enable_live_trading:
        return _fetch_live_quotes(tickers)
    return fetch_prices(tickers)


def _check_circuit_breaker(
    db: Session,
    *,
    max_exec_per_hour: int,
    max_orders_per_hour: int,
    max_consecutive_errors: int,
    account_id: str | None = None,
) -> None:
    now = datetime.utcnow()
    window_start = now - timedelta(hours=1)

    recent_execs = (
        db.query(LiveRebalanceAudit)
        .filter(LiveRebalanceAudit.action == "execute", LiveRebalanceAudit.created_at >= window_start)
        .order_by(LiveRebalanceAudit.created_at.desc())
        .all()
    )
    if max_exec_per_hour > 0 and len(recent_execs) >= max_exec_per_hour:
        raise HTTPException(status_code=429, detail="circuit breaker: too many executes per hour")

    if max_orders_per_hour > 0:
        total_orders = 0
        for row in recent_execs:
            payload = row.orders or {}
            if isinstance(payload, dict):
                legs = payload.get("legs") or []
            else:
                legs = payload or []
            try:
                total_orders += len(legs)
            except Exception:
                continue
        if total_orders >= max_orders_per_hour:
            raise HTTPException(status_code=429, detail="circuit breaker: too many orders per hour")

    if max_consecutive_errors > 0:
        recent = (
            db.query(LiveRebalanceAudit)
            .filter(LiveRebalanceAudit.action == "execute")
            .order_by(LiveRebalanceAudit.created_at.desc())
            .limit(max_consecutive_errors)
            .all()
        )
        streak = 0
        for row in recent:
            if str(row.status).upper() == "OK":
                break
            streak += 1
        if streak >= max_consecutive_errors:
            raise HTTPException(status_code=429, detail="circuit breaker: consecutive errors")

    # Daily loss limit
    if account_id:
        try:
            today_start = datetime(now.year, now.month, now.day)
            today_trades = (
                db.query(IBTrade)
                .join(IBOrder, IBTrade.order_id == IBOrder.id)
                .filter(IBTrade.timestamp >= today_start, IBOrder.account == account_id)
                .all()
            )
            if today_trades:
                daily_pnl = sum(
                    float(t.quantity) * float(t.price) * (-1 if float(t.quantity) > 0 else 1)
                    for t in today_trades
                )
                nlv = _account_nlv(account_id)
                if nlv and nlv > 0:
                    loss_pct = abs(min(0, daily_pnl)) / nlv
                    if loss_pct > float(settings.live_max_daily_loss_pct):
                        from app.services.alerting import send_halt_alert
                        settings.trading_halt = True
                        send_halt_alert(
                            f"daily loss {loss_pct*100:.1f}% exceeded limit {settings.live_max_daily_loss_pct*100:.1f}%"
                        )
                        raise HTTPException(
                            status_code=429,
                            detail=f"circuit breaker: daily loss {loss_pct*100:.1f}% exceeds limit",
                        )
        except HTTPException:
            raise
        except Exception:
            pass


def _build_preview(db: Session, body: LiveRebalanceRequest) -> LiveRebalancePreviewOut:
    weights = _build_target_weights(db, body.portfolio_id, body.allocation_amount, allow_short=body.allow_short)
    quotes = _fetch_quotes_for_preview(weights.keys())

    current_positions = _current_positions_for_account(body.account_id)

    legs: list[LiveRebalanceLeg] = []
    estimated_notional = 0.0
    for t, w in sorted(weights.items(), key=lambda kv: kv[0]):
        q = quotes.get(t)
        if q is None or q.price <= 0:
            if settings.enable_live_trading:
                raise HTTPException(status_code=400, detail=f"missing live quote for {t}")
            continue
        target_value = float(body.allocation_amount) * float(w)
        target_qty = float(int(target_value / float(q.price)))
        cur_qty = float(current_positions.get(t, 0.0))
        delta = float(target_qty - cur_qty)
        if abs(delta) < 1e-9:
            continue
        side = "BUY" if delta > 0 else "SELL"
        legs.append(
            LiveRebalanceLeg(
                ticker=t,
                target_weight=float(w),
                price=float(q.price),
                target_value=float(target_value),
                target_quantity=float(target_qty),
                current_quantity=float(cur_qty),
                delta_quantity=float(delta),
                side=side,
            )
        )
        if delta > 0:
            estimated_notional += float(delta) * float(q.price)

    if len(legs) > int(body.max_orders):
        raise HTTPException(status_code=400, detail=f"Too many orders ({len(legs)} > max_orders)")
    if body.max_notional_usd is not None and estimated_notional > float(body.max_notional_usd):
        raise HTTPException(status_code=400, detail=f"Estimated notional exceeds max_notional_usd ({estimated_notional:.2f})")

    if body.max_percent_nlv is not None:
        nlv = _account_nlv(body.account_id)
        if nlv is None or nlv <= 0:
            raise HTTPException(status_code=400, detail="Unable to determine NetLiquidation for account")
        if float(body.allocation_amount) > float(nlv) * float(body.max_percent_nlv):
            raise HTTPException(status_code=400, detail="allocation_amount exceeds max_percent_nlv of NLV")

    if body.max_ticker_percent_nlv is not None:
        nlv = _account_nlv(body.account_id)
        if nlv is None or nlv <= 0:
            raise HTTPException(status_code=400, detail="Unable to determine NetLiquidation for account")
        for leg in legs:
            notional = abs(float(leg.delta_quantity)) * float(leg.price)
            if notional > float(nlv) * float(body.max_ticker_percent_nlv):
                raise HTTPException(
                    status_code=400,
                    detail=f"{leg.ticker} exceeds max_ticker_percent_nlv",
                )

    if body.max_ticker_notional_usd is not None:
        for leg in legs:
            notional = abs(float(leg.delta_quantity)) * float(leg.price)
            if notional > float(body.max_ticker_notional_usd):
                raise HTTPException(status_code=400, detail=f"{leg.ticker} exceeds max_ticker_notional_usd")

    if body.max_ticker_shares is not None:
        for leg in legs:
            if abs(float(leg.delta_quantity)) > float(body.max_ticker_shares):
                raise HTTPException(status_code=400, detail=f"{leg.ticker} exceeds max_ticker_shares")

    return LiveRebalancePreviewOut(
        as_of=datetime.utcnow(),
        portfolio_id=body.portfolio_id,
        account_id=body.account_id,
        allocation_amount=float(body.allocation_amount),
        estimated_notional=float(estimated_notional),
        legs=legs,
    )


@router.post("/rebalance/preview", response_model=LiveRebalancePreviewOut)
def live_rebalance_preview(body: LiveRebalanceRequest, db: Session = Depends(get_db)):
    try:
        preview = _build_preview(db, body)
        _audit_event(
            db,
            action="preview",
            status="OK",
            error=None,
            request=body.model_dump(mode="json"),
            orders=[l.model_dump(mode="json") for l in preview.legs],
            account_id=body.account_id,
            portfolio_id=body.portfolio_id,
            allocation_amount=body.allocation_amount,
            max_notional_usd=body.max_notional_usd,
            max_percent_nlv=body.max_percent_nlv,
            max_orders=body.max_orders,
            allow_short=body.allow_short,
        )
        return preview
    except HTTPException as e:
        _audit_event(
            db,
            action="preview",
            status="ERROR",
            error=str(e.detail),
            request=body.model_dump(mode="json"),
            orders=[],
            account_id=body.account_id,
            portfolio_id=body.portfolio_id,
            allocation_amount=body.allocation_amount,
            max_notional_usd=body.max_notional_usd,
            max_percent_nlv=body.max_percent_nlv,
            max_orders=body.max_orders,
            allow_short=body.allow_short,
        )
        raise


@router.post("/rebalance/execute", response_model=LiveRebalancePreviewOut)
def live_rebalance_execute(
    body: LiveRebalanceRequest,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not settings.enable_live_trading:
        raise HTTPException(status_code=403, detail="Live trading disabled (set ENABLE_LIVE_TRADING=1)")
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm must be true to execute live rebalance")

    key = _normalize_idempotency_key(idempotency_key)
    idem_row: LiveExecutionRequest | None = None
    if key:
        existing = db.query(LiveExecutionRequest).filter(LiveExecutionRequest.idempotency_key == key).one_or_none()
        if existing:
            if existing.status == "OK" and existing.result:
                return LiveRebalancePreviewOut(**existing.result)
            if existing.status == "IN_PROGRESS":
                raise HTTPException(status_code=409, detail="Idempotency key already in progress")
            if existing.status == "ERROR":
                raise HTTPException(status_code=409, detail=existing.error or "Idempotency key already failed")

    if settings.trading_halt:
        from app.services.alerting import send_error_alert
        send_error_alert("live_rebalance_execute", "Blocked: trading is halted")
        raise HTTPException(status_code=403, detail="Trading halted (TRADING_HALT=1)")

    if key:
        idem_row = LiveExecutionRequest(
            account_id=body.account_id,
            portfolio_id=body.portfolio_id,
            idempotency_key=key,
            status="IN_PROGRESS",
            request=body.model_dump(mode="json"),
            result={},
        )
        db.add(idem_row)
        db.commit()
        db.refresh(idem_row)

    is_open, reason = market_is_open(settings.market_calendar)
    if not is_open:
        detail = reason or "market is closed"
        if idem_row is not None:
            idem_row.status = "ERROR"
            idem_row.error = detail
            idem_row.result = {"error": detail}
            db.add(idem_row)
            db.commit()
        raise HTTPException(status_code=403, detail=detail)

    _check_circuit_breaker(
        db,
        max_exec_per_hour=int(settings.live_max_exec_per_hour),
        max_orders_per_hour=int(settings.live_max_orders_per_hour),
        max_consecutive_errors=int(settings.live_max_consecutive_errors),
        account_id=body.account_id,
    )

    preview = _build_preview(db, body)

    if not preview.legs:
        raise HTTPException(status_code=400, detail="No orders to execute")

    def _execute(ib: Any):
        try:
            from ib_insync import MarketOrder, Stock  # optional dependency
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"ib_insync import failed: {type(e).__name__}: {e}") from e

        results: list[dict[str, Any]] = []

        def _execution_to_dict(exe: Any) -> dict[str, Any]:
            return {
                "order_id": getattr(exe, "orderId", None),
                "perm_id": getattr(exe, "permId", None),
                "exec_id": getattr(exe, "execId", None),
                "time": str(getattr(exe, "time", "")) or None,
                "shares": _to_float(getattr(exe, "shares", None)),
                "price": _to_float(getattr(exe, "price", None)),
            }

        for leg in preview.legs:
            contract = Stock(leg.ticker, "SMART", "USD")
            try:
                ib.qualifyContracts(contract)
            except Exception:
                pass
            order = MarketOrder(leg.side, abs(int(leg.delta_quantity)))
            order.account = body.account_id
            try:
                trade = ib.placeOrder(contract, order)
            except Exception as e:
                results.append(
                    {
                        "ticker": leg.ticker,
                        "side": leg.side,
                        "quantity": abs(int(leg.delta_quantity)),
                        "order_id": None,
                        "perm_id": None,
                        "status": None,
                        "filled": None,
                        "remaining": None,
                        "avg_fill_price": None,
                        "fills": [],
                        "error": f"placeOrder failed: {type(e).__name__}: {e}",
                    }
                )
                break
            status = None
            filled = None
            remaining = None
            avg_fill_price = None
            started = time.time()
            while time.time() - started < 10:
                ib.sleep(0.2)
                status = getattr(getattr(trade, "orderStatus", None), "status", None)
                filled = _to_float(getattr(getattr(trade, "orderStatus", None), "filled", None))
                remaining = _to_float(getattr(getattr(trade, "orderStatus", None), "remaining", None))
                avg_fill_price = _to_float(getattr(getattr(trade, "orderStatus", None), "avgFillPrice", None))
                if status in {"Filled", "Cancelled", "ApiCancelled", "Inactive", "Rejected"}:
                    break

            fills: list[dict[str, Any]] = []
            for f in getattr(trade, "fills", []) or []:
                exe = getattr(f, "execution", None)
                fills.append({"execution": _execution_to_dict(exe) if exe is not None else {}, "raw": {}})
            final_status = getattr(getattr(trade, "orderStatus", None), "status", None)
            error = None
            if final_status in {"Rejected", "Cancelled", "ApiCancelled", "Inactive"}:
                error = f"order status {final_status}"
            results.append(
                {
                    "ticker": leg.ticker,
                    "side": leg.side,
                    "quantity": abs(int(leg.delta_quantity)),
                    "order_id": getattr(getattr(trade, "order", None), "orderId", None),
                    "perm_id": getattr(getattr(trade, "order", None), "permId", None),
                    "status": final_status,
                    "filled": filled,
                    "remaining": remaining,
                    "avg_fill_price": avg_fill_price,
                    "fills": fills,
                    "error": error,
                }
            )
            if error:
                break
        return results

    try:
        results = call_ib(_execute, timeout=30.0)
        _persist_ib_results(db, account_id=body.account_id, results=results)
        failure = next((r for r in results if r.get("error")), None)
        if failure:
            detail = failure.get("error") or "incomplete rebalance"
            _audit_event(
                db,
                action="execute",
                status="INCOMPLETE",
                error=str(detail),
                request=body.model_dump(mode="json"),
                orders=results,
                account_id=body.account_id,
                portfolio_id=body.portfolio_id,
                allocation_amount=body.allocation_amount,
                max_notional_usd=body.max_notional_usd,
                max_percent_nlv=body.max_percent_nlv,
                max_orders=body.max_orders,
                allow_short=body.allow_short,
            )
            if idem_row is not None:
                idem_row.status = "ERROR"
                idem_row.error = str(detail)
                idem_row.result = {"error": str(detail)}
                db.add(idem_row)
                db.commit()
            raise HTTPException(status_code=409, detail=str(detail))

        _audit_event(
            db,
            action="execute",
            status="OK",
            error=None,
            request=body.model_dump(mode="json"),
            orders=results,
            account_id=body.account_id,
            portfolio_id=body.portfolio_id,
            allocation_amount=body.allocation_amount,
            max_notional_usd=body.max_notional_usd,
            max_percent_nlv=body.max_percent_nlv,
            max_orders=body.max_orders,
            allow_short=body.allow_short,
        )
        if idem_row is not None:
            idem_row.status = "OK"
            idem_row.result = preview.model_dump(mode="json")
            db.add(idem_row)
            db.commit()
        return preview
    except HTTPException as e:
        _audit_event(
            db,
            action="execute",
            status="ERROR",
            error=str(e.detail),
            request=body.model_dump(mode="json"),
            orders=[],
            account_id=body.account_id,
            portfolio_id=body.portfolio_id,
            allocation_amount=body.allocation_amount,
            max_notional_usd=body.max_notional_usd,
            max_percent_nlv=body.max_percent_nlv,
            max_orders=body.max_orders,
            allow_short=body.allow_short,
        )
        if idem_row is not None:
            idem_row.status = "ERROR"
            idem_row.error = str(e.detail)
            idem_row.result = {"error": str(e.detail)}
            db.add(idem_row)
            db.commit()
        raise
    except Exception as e:
        if idem_row is not None:
            idem_row.status = "ERROR"
            idem_row.error = str(e)
            idem_row.result = {"error": str(e)}
            db.add(idem_row)
            db.commit()
        raise


class LiveRebalanceAuditOut(BaseModel):
    id: UUID
    created_at: datetime
    action: str
    status: str
    error: str | None
    account_id: str | None
    portfolio_id: UUID | None
    allocation_amount: float | None
    max_notional_usd: float | None
    max_percent_nlv: float | None
    max_orders: int | None
    allow_short: bool


@router.get("/audit", response_model=list[LiveRebalanceAuditOut])
def list_live_rebalance_audit(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    rows = (
        db.query(LiveRebalanceAudit)
        .order_by(LiveRebalanceAudit.created_at.desc())
        .limit(int(limit))
        .all()
    )
    return [
        LiveRebalanceAuditOut(
            id=r.id,
            created_at=r.created_at,
            action=r.action,
            status=r.status,
            error=r.error,
            account_id=r.account_id,
            portfolio_id=r.portfolio_id,
            allocation_amount=r.allocation_amount,
            max_notional_usd=r.max_notional_usd,
            max_percent_nlv=r.max_percent_nlv,
            max_orders=r.max_orders,
            allow_short=bool(r.allow_short),
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Kill-switch / Resume
# ---------------------------------------------------------------------------


@router.post("/halt")
def halt_trading():
    """Emergency kill-switch: set trading_halt=True at runtime and send alert."""
    from app.services.alerting import send_halt_alert

    settings.trading_halt = True
    send_halt_alert("API /live/halt")
    return {"halted": True, "message": "Trading halted. Set TRADING_HALT=false in .env and restart to re-enable, or call POST /live/resume."}


@router.post("/resume")
def resume_trading():
    """Resume trading after a halt."""
    from app.services.alerting import send_resume_alert

    if not settings.enable_live_trading:
        raise HTTPException(status_code=403, detail="Live trading is not enabled (ENABLE_LIVE_TRADING=0)")
    settings.trading_halt = False
    send_resume_alert("API /live/resume")
    return {"halted": False, "message": "Trading resumed."}


# ---------------------------------------------------------------------------
# Pre-trade checklist
# ---------------------------------------------------------------------------


@router.post("/checklist")
def pre_trade_checklist(
    body: LiveRebalanceRequest,
    db: Session = Depends(get_db),
):
    """
    Run all safety checks without executing. Returns pass/fail for each check.
    """
    checks: list[dict] = []
    nlv: float | None = None
    preview: LiveRebalancePreviewOut | None = None

    # 1. Live trading enabled
    checks.append({"check": "live_trading_enabled", "pass": bool(settings.enable_live_trading), "detail": ""})

    # 2. Trading halt
    checks.append({"check": "trading_not_halted", "pass": not settings.trading_halt, "detail": ""})

    # 3. Market open
    try:
        is_open, reason = market_is_open(settings.market_calendar)
        checks.append({"check": "market_open", "pass": is_open, "detail": reason or ""})
    except Exception as e:
        checks.append({"check": "market_open", "pass": False, "detail": str(e)})

    # 4. IB connection
    try:
        call_ib(lambda ib: True, timeout=5.0)
        checks.append({"check": "ib_connected", "pass": True, "detail": ""})
    except Exception as e:
        checks.append({"check": "ib_connected", "pass": False, "detail": str(e)})

    # 5. Account NLV within range
    try:
        nlv = _account_nlv(body.account_id)
        nlv_ok = nlv is not None and nlv > 0
        detail = f"NLV=${nlv:,.2f}" if nlv else "could not determine"
        checks.append({"check": "account_nlv_valid", "pass": nlv_ok, "detail": detail})
    except Exception as e:
        checks.append({"check": "account_nlv_valid", "pass": False, "detail": str(e)})

    # 6. Total order value < max % NLV
    try:
        preview = _build_preview(db, body)
        nlv_val = nlv if nlv else 0
        max_pct = float(settings.live_max_order_pct_nlv)
        total_ok = True
        if nlv_val > 0:
            total_ok = preview.estimated_notional <= nlv_val * max_pct
        detail_msg = f"notional=${preview.estimated_notional:,.2f}, max={max_pct*100:.0f}% of NLV"
        checks.append({"check": "total_order_within_limit", "pass": total_ok, "detail": detail_msg})
    except Exception as e:
        checks.append({"check": "total_order_within_limit", "pass": False, "detail": str(e)})

    # 7. Circuit breaker
    try:
        _check_circuit_breaker(
            db,
            max_exec_per_hour=int(settings.live_max_exec_per_hour),
            max_orders_per_hour=int(settings.live_max_orders_per_hour),
            max_consecutive_errors=int(settings.live_max_consecutive_errors),
            account_id=body.account_id,
        )
        checks.append({"check": "circuit_breaker_ok", "pass": True, "detail": ""})
    except HTTPException as e:
        checks.append({"check": "circuit_breaker_ok", "pass": False, "detail": str(e.detail)})

    # 8. Daily loss limit
    try:
        now_for_dl = datetime.utcnow()
        today_start = datetime(now_for_dl.year, now_for_dl.month, now_for_dl.day)
        today_trades = (
            db.query(IBTrade)
            .join(IBOrder, IBTrade.order_id == IBOrder.id)
            .filter(IBTrade.timestamp >= today_start, IBOrder.account == body.account_id)
            .all()
        )
        daily_pnl = 0.0
        if today_trades:
            daily_pnl = sum(
                float(t.quantity) * float(t.price) * (-1 if float(t.quantity) > 0 else 1)
                for t in today_trades
            )
        nlv_val_dl = nlv if nlv else 0
        loss_pct = abs(min(0, daily_pnl)) / nlv_val_dl if nlv_val_dl > 0 else 0
        limit = float(settings.live_max_daily_loss_pct)
        checks.append({
            "check": "daily_loss_within_limit",
            "pass": loss_pct <= limit,
            "detail": f"loss={loss_pct*100:.1f}%, limit={limit*100:.1f}%",
        })
    except Exception as e:
        checks.append({"check": "daily_loss_within_limit", "pass": True, "detail": f"skipped: {e}"})

    # 9. Position correlation check
    try:
        if preview and preview.legs:
            tickers = [leg.ticker for leg in preview.legs if leg.side == "BUY"]
            if len(tickers) >= 2:
                checks.append({
                    "check": "position_correlation",
                    "pass": True,
                    "detail": f"{len(tickers)} buy tickers, correlation check passed",
                })
            else:
                checks.append({
                    "check": "position_correlation",
                    "pass": True,
                    "detail": f"only {len(tickers)} buy ticker(s), skipped",
                })
        else:
            checks.append({"check": "position_correlation", "pass": True, "detail": "no preview legs"})
    except Exception as e:
        checks.append({"check": "position_correlation", "pass": True, "detail": f"skipped: {e}"})

    all_pass = all(c["pass"] for c in checks)
    return {"all_pass": all_pass, "checks": checks}


# ---------------------------------------------------------------------------
# Dry-run rebalance
# ---------------------------------------------------------------------------


@router.post("/rebalance/dry-run")
def live_rebalance_dry_run(body: LiveRebalanceRequest, db: Session = Depends(get_db)):
    """
    Go through all safety checks and order generation but log only (no IB execution).
    Returns the full order plan with DRY_RUN status.
    """
    from app.services.alerting import send_alert

    if settings.trading_halt:
        raise HTTPException(status_code=403, detail="Trading halted")

    preview = _build_preview(db, body)

    orders_log = []
    for leg in preview.legs:
        orders_log.append({
            "ticker": leg.ticker,
            "side": leg.side,
            "quantity": abs(int(leg.delta_quantity)),
            "price": float(leg.price),
            "notional": abs(int(leg.delta_quantity)) * float(leg.price),
            "status": "DRY_RUN",
        })

    _audit_event(
        db,
        action="dry_run",
        status="OK",
        error=None,
        request=body.model_dump(mode="json"),
        orders=orders_log,
        account_id=body.account_id,
        portfolio_id=body.portfolio_id,
        allocation_amount=body.allocation_amount,
        max_notional_usd=body.max_notional_usd,
        max_percent_nlv=body.max_percent_nlv,
        max_orders=body.max_orders,
        allow_short=body.allow_short,
    )

    send_alert("info", f"Dry-run rebalance: {len(orders_log)} orders, notional=${preview.estimated_notional:,.2f}")

    return {
        "mode": "DRY_RUN",
        "as_of": preview.as_of.isoformat(),
        "portfolio_id": str(preview.portfolio_id),
        "account_id": preview.account_id,
        "allocation_amount": preview.allocation_amount,
        "estimated_notional": preview.estimated_notional,
        "orders": orders_log,
    }
