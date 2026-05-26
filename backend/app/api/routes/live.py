from __future__ import annotations

from datetime import datetime, timedelta
import time
from typing import Any, Iterable
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.ib_audit import IBOrder, IBTrade, LiveExecutionRequest, LiveRebalanceAudit, SystemState
from app.models.portfolio import Portfolio, PortfolioStrategy
from app.services.ib_worker import call_ib
from app.services.market_calendar import market_is_open
from app.services.paper_trading import PriceQuote, fetch_last_close_price, fetch_prices

router = APIRouter()

TERMINAL_STATUSES = frozenset({"Filled", "Cancelled", "ApiCancelled", "Inactive", "Rejected"})

# ---------------------------------------------------------------------------
# IB account whitelist cache
# ---------------------------------------------------------------------------

_managed_accounts_cache: list[str] = []
_managed_accounts_cache_at: float = 0.0
_MANAGED_ACCOUNTS_TTL = 300.0  # 5 minutes


def _assert_account_allowed(account_id: str) -> None:
    """Raise 400 if account_id is not in IB managed accounts or LIVE_ALLOWED_ACCOUNTS."""
    global _managed_accounts_cache, _managed_accounts_cache_at
    now = time.time()
    if now - _managed_accounts_cache_at > _MANAGED_ACCOUNTS_TTL or not _managed_accounts_cache:
        from app.api.routes.ib import _managed_accounts
        cached = call_ib(lambda ib: _managed_accounts(ib), timeout=10.0)
        _managed_accounts_cache = [str(a) for a in (cached or []) if a]
        _managed_accounts_cache_at = now

    if _managed_accounts_cache and account_id not in _managed_accounts_cache:
        raise HTTPException(
            status_code=400,
            detail=f"account_id {account_id!r} not in IB managed accounts",
        )

    allowed_raw = settings.live_allowed_accounts
    if allowed_raw:
        allowed = [a.strip() for a in allowed_raw.replace(";", ",").split(",") if a.strip()]
        if allowed and account_id not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"account_id {account_id!r} not in LIVE_ALLOWED_ACCOUNTS allowlist",
            )


# ---------------------------------------------------------------------------
# Persistent halt helpers
# ---------------------------------------------------------------------------


def _load_halt_from_db(db: Session) -> bool:
    row = db.query(SystemState).filter(SystemState.key == "trading_halt").one_or_none()
    if row is not None:
        return str(row.value).lower() in {"1", "true", "yes"}
    return False


def _persist_halt(db: Session, halted: bool) -> None:
    row = db.query(SystemState).filter(SystemState.key == "trading_halt").one_or_none()
    now = datetime.utcnow()
    if row is None:
        row = SystemState(key="trading_halt", value=str(int(halted)), updated_at=now)
        db.add(row)
    else:
        row.value = str(int(halted))
        row.updated_at = now
    db.commit()


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------


@router.get("/status")
def live_status():
    return {
        "enabled": bool(settings.enable_live_trading),
        "dry_run": bool(settings.live_dry_run),
        "dry_run_blocks_execute": bool(settings.live_dry_run),
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


def _quantize_qty(qty: float) -> float:
    """Round a share quantity per the fractional-shares setting.

    Fractional ON  -> round to LIVE_FRACTIONAL_DECIMALS places (keeps fractions).
    Fractional OFF -> truncate toward zero to a whole share (legacy behaviour).
    """
    q = float(qty)
    if settings.live_fractional_shares:
        return round(q, int(settings.live_fractional_decimals))
    # preserve sign while truncating magnitude (legacy used int())
    return float(int(q))


def _order_qty(delta: float) -> float:
    """Absolute order quantity for a leg, respecting the fractional setting."""
    return abs(_quantize_qty(delta))


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


def _extract_realized_pnl(summary_rows: list[Any]) -> float | None:
    for row in summary_rows or []:
        tag = str(getattr(row, "tag", "") or "")
        ccy = str(getattr(row, "currency", "") or "")
        if tag != "RealizedPnL":
            continue
        if ccy not in {"USD", "BASE", ""}:
            continue
        val = _to_float(getattr(row, "value", None))
        if val is not None:
            return float(val)
    return None


def _extract_unrealized_pnl(summary_rows: list[Any]) -> float | None:
    for row in summary_rows or []:
        tag = str(getattr(row, "tag", "") or "")
        ccy = str(getattr(row, "currency", "") or "")
        if tag != "UnrealizedPnL":
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


def _account_realized_pnl(account_id: str) -> float | None:
    """Read RealizedPnL from IB accountSummary (today's session P&L)."""
    from app.api.routes.ib import _account_values_for_account

    rows = call_ib(lambda ib: _account_values_for_account(ib, account_id), timeout=15.0)
    return _extract_realized_pnl(rows or [])


def _account_total_pnl(account_id: str) -> tuple[float | None, float | None]:
    """Return (realized_pnl, unrealized_pnl) from IB accountSummary in one call."""
    from app.api.routes.ib import _account_values_for_account

    rows = call_ib(lambda ib: _account_values_for_account(ib, account_id), timeout=15.0) or []
    return _extract_realized_pnl(rows), _extract_unrealized_pnl(rows)


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

    # Daily loss limit — read from IB accountSummary (RealizedPnL + UnrealizedPnL).
    # Both legs are required so a large unrealised drawdown triggers the halt even
    # before positions are closed — preventing a strategy from digging deeper.
    if account_id:
        try:
            realized_pnl, unrealized_pnl = _account_total_pnl(account_id)
            nlv = _account_nlv(account_id)
            if nlv and nlv > 0:
                r = realized_pnl or 0.0
                u = unrealized_pnl or 0.0
                total_pnl = r + u
                if total_pnl < 0:
                    loss_pct = abs(total_pnl) / nlv
                    if loss_pct > float(settings.live_max_daily_loss_pct):
                        from app.services.alerting import send_halt_alert
                        settings.trading_halt = True
                        try:
                            _persist_halt(db, True)
                        except Exception:
                            pass
                        send_halt_alert(
                            f"daily loss {loss_pct*100:.1f}% exceeded limit "
                            f"{settings.live_max_daily_loss_pct*100:.1f}% "
                            f"(realized={r:+.2f} unrealized={u:+.2f}) — trading halted"
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
        # Skip dust legs whose target value is below the per-leg minimum (fractional mode only;
        # in whole-share mode sub-$min targets already truncate to 0 shares).
        if settings.live_fractional_shares and target_value < float(settings.live_min_leg_usd):
            continue
        target_qty = _quantize_qty(target_value / float(q.price))
        cur_qty = float(current_positions.get(t, 0.0))
        delta = float(target_qty - cur_qty)
        min_delta = 10.0 ** (-int(settings.live_fractional_decimals)) if settings.live_fractional_shares else 1e-9
        if abs(delta) < min_delta:
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
@limiter.limit("5/minute")
def live_rebalance_execute(
    request: Request,
    body: LiveRebalanceRequest,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return execute_live_rebalance_core(db, body, idempotency_key)


def execute_live_rebalance_core(
    db: Session,
    body: LiveRebalanceRequest,
    idempotency_key: str | None,
) -> LiveRebalancePreviewOut:
    """Gated live-rebalance execution, callable from the HTTP route or the
    scheduler. All hard gates (live-enabled, dry-run, halt, idempotency,
    account allowlist, market-open, circuit breaker, NLV cap) live here."""
    if not settings.enable_live_trading:
        raise HTTPException(status_code=403, detail="Live trading disabled (set ENABLE_LIVE_TRADING=1)")
    if settings.live_dry_run:
        raise HTTPException(
            status_code=403,
            detail="Dry-run mode active (LIVE_DRY_RUN=true). Use POST /live/rebalance/dry-run instead.",
        )
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm must be true to execute live rebalance")

    # Phase 1: Mandatory idempotency key
    key = _normalize_idempotency_key(idempotency_key)
    if not key:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key header is required for execute",
        )

    idem_row: LiveExecutionRequest | None = None
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

    # Phase 1: Account whitelist check
    _assert_account_allowed(body.account_id)

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

    # Phase 2: Server-side NLV cap — enforced here, not just in checklist
    nlv_for_cap = _account_nlv(body.account_id)
    if nlv_for_cap and nlv_for_cap > 0:
        cap = float(nlv_for_cap) * float(settings.live_max_order_pct_nlv)
        if float(preview.estimated_notional) > cap:
            detail = (
                f"estimated notional ${preview.estimated_notional:,.2f} exceeds "
                f"LIVE_MAX_ORDER_PCT_NLV cap ${cap:,.2f} "
                f"({settings.live_max_order_pct_nlv*100:.0f}% of NLV ${nlv_for_cap:,.2f})"
            )
            idem_row.status = "ERROR"
            idem_row.error = detail
            idem_row.result = {"error": detail}
            db.add(idem_row)
            db.commit()
            raise HTTPException(status_code=403, detail=detail)

    per_leg_timeout = float(settings.live_per_leg_timeout_seconds)
    execute_timeout = len(preview.legs) * per_leg_timeout + 60.0

    def _execute(ib: Any):
        try:
            from ib_insync import MarketOrder, Stock  # optional dependency
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"ib_insync import failed: {type(e).__name__}: {e}") from e

        results: list[dict[str, Any]] = []
        placed_trades: list[Any] = []  # orders we placed this rebalance (for scoped cancel)

        # Anti-duplicate guard: if this account already has open orders at IB, do not
        # stack a new rebalance on top (protects against the crash-to-retry duplicate path).
        try:
            existing_open = [
                o for o in (ib.reqAllOpenOrders() or [])
                if getattr(getattr(o, "order", None), "account", None) in (None, body.account_id)
            ]
        except Exception:
            existing_open = []
        if existing_open:
            raise HTTPException(
                status_code=409,
                detail=f"account {body.account_id} has {len(existing_open)} open order(s) at IB; "
                       "clear or reconcile them before executing a new rebalance",
            )

        def _cancel_placed(ib_: Any) -> None:
            # Cancel ONLY the orders this rebalance placed (scoped), never gateway-wide,
            # so concurrent rebalances on other sub-accounts are unaffected.
            for tr in placed_trades:
                try:
                    st = getattr(getattr(tr, "orderStatus", None), "status", None)
                    if st in TERMINAL_STATUSES:
                        continue
                    ord_obj = getattr(tr, "order", None)
                    if ord_obj is not None:
                        ib_.cancelOrder(ord_obj)
                except Exception:
                    pass

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
            # Phase 1: Cooperative halt check between legs
            if settings.trading_halt:
                _cancel_placed(ib)
                results.append(
                    {
                        "ticker": leg.ticker,
                        "side": leg.side,
                        "quantity": _order_qty(leg.delta_quantity),
                        "order_id": None,
                        "perm_id": None,
                        "status": "Cancelled",
                        "filled": None,
                        "remaining": None,
                        "avg_fill_price": None,
                        "fills": [],
                        "error": "trading halted mid-rebalance",
                    }
                )
                break

            contract = Stock(leg.ticker, "SMART", "USD")
            try:
                ib.qualifyContracts(contract)
            except Exception:
                pass
            order = MarketOrder(leg.side, _order_qty(leg.delta_quantity))
            order.account = body.account_id
            try:
                trade = ib.placeOrder(contract, order)
                placed_trades.append(trade)
            except Exception as e:
                _cancel_placed(ib)
                results.append(
                    {
                        "ticker": leg.ticker,
                        "side": leg.side,
                        "quantity": _order_qty(leg.delta_quantity),
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

            # Phase 1: Wait for terminal status up to per_leg_timeout
            deadline = time.time() + per_leg_timeout
            while time.time() < deadline:
                ib.sleep(0.2)
                status = getattr(getattr(trade, "orderStatus", None), "status", None)
                if status in TERMINAL_STATUSES:
                    break

            final_status = getattr(getattr(trade, "orderStatus", None), "status", None)
            filled = _to_float(getattr(getattr(trade, "orderStatus", None), "filled", None))
            remaining = _to_float(getattr(getattr(trade, "orderStatus", None), "remaining", None))
            avg_fill_price = _to_float(getattr(getattr(trade, "orderStatus", None), "avgFillPrice", None))

            timed_out = final_status not in TERMINAL_STATUSES
            if timed_out:
                # Phase 1: abort remaining legs, cancel in-flight order
                _cancel_placed(ib)

            fills: list[dict[str, Any]] = []
            for f in getattr(trade, "fills", []) or []:
                exe = getattr(f, "execution", None)
                fills.append({"execution": _execution_to_dict(exe) if exe is not None else {}, "raw": {}})

            error = None
            if timed_out:
                error = f"fill timeout after {per_leg_timeout:.0f}s (last_status={final_status})"
            elif final_status in {"Rejected", "Cancelled", "ApiCancelled", "Inactive"}:
                error = f"order status {final_status}"

            results.append(
                {
                    "ticker": leg.ticker,
                    "side": leg.side,
                    "quantity": _order_qty(leg.delta_quantity),
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
        results = call_ib(_execute, timeout=execute_timeout)
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
            from app.services.alerting import send_rebalance_alert
            completed = len([r for r in results if not r.get("error")])
            send_rebalance_alert(
                "INCOMPLETE",
                f"Account: {body.account_id}\n"
                f"Error: {detail}\n"
                f"Completed: {completed} / {len(preview.legs)} legs",
            )
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

        # Post-execute reconciliation: verify resulting positions match target, so an
        # "OK" status can't silently hide partial fills / drift. Non-fatal by design.
        try:
            actual = _current_positions_for_account(body.account_id)
            target = {l.ticker: float(l.target_quantity) for l in preview.legs}
            tickers = set(actual) | set(target)
            drifts = []
            for t in tickers:
                a = float(actual.get(t, 0.0))
                tq = float(target.get(t, 0.0))
                px = next((float(l.price) for l in preview.legs if l.ticker == t), 0.0)
                if abs(a - tq) * (px or 0.0) > max(50.0, 0.001 * float(body.allocation_amount)):
                    drifts.append({"ticker": t, "target_qty": tq, "actual_qty": a,
                                   "drift_qty": round(a - tq, 4), "px": px})
            if drifts:
                idem_row.result = {**preview.model_dump(mode="json"), "reconciliation_drift": drifts}
                from app.services.alerting import send_rebalance_alert as _sra
                _sra("DRIFT", f"Account {body.account_id}: {len(drifts)} position(s) off target after rebalance: "
                              + ", ".join(f"{d['ticker']}({d['drift_qty']:+g})" for d in drifts[:8]))
        except Exception:
            pass

        idem_row.status = "OK"
        if not isinstance(idem_row.result, dict) or "reconciliation_drift" not in (idem_row.result or {}):
            idem_row.result = preview.model_dump(mode="json")
        db.add(idem_row)
        db.commit()
        from app.services.alerting import send_rebalance_alert
        legs_summary = ", ".join(
            f"{l.side} {_order_qty(l.delta_quantity)} {l.ticker}" for l in preview.legs[:5]
        )
        if len(preview.legs) > 5:
            legs_summary += f" (+{len(preview.legs) - 5} more)"
        send_rebalance_alert(
            "OK",
            f"Account: {body.account_id}\n"
            f"Portfolio: {body.portfolio_id}\n"
            f"Notional: ${preview.estimated_notional:,.2f}\n"
            f"Orders: {legs_summary}",
        )
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
        idem_row.status = "ERROR"
        idem_row.error = str(e.detail)
        idem_row.result = {"error": str(e.detail)}
        db.add(idem_row)
        db.commit()
        raise
    except Exception as e:
        idem_row.status = "ERROR"
        idem_row.error = str(e)
        idem_row.result = {"error": str(e)}
        db.add(idem_row)
        db.commit()
        raise


# ---------------------------------------------------------------------------
# Audit endpoints
# ---------------------------------------------------------------------------


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


class LiveRebalanceAuditDetailOut(LiveRebalanceAuditOut):
    request: dict
    orders: dict


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


@router.get("/audit/{audit_id}", response_model=LiveRebalanceAuditDetailOut)
def get_live_rebalance_audit(audit_id: UUID, db: Session = Depends(get_db)):
    """Return full request + orders payload for forensic replay."""
    row = db.query(LiveRebalanceAudit).filter(LiveRebalanceAudit.id == str(audit_id)).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit record not found")
    return LiveRebalanceAuditDetailOut(
        id=row.id,
        created_at=row.created_at,
        action=row.action,
        status=row.status,
        error=row.error,
        account_id=row.account_id,
        portfolio_id=row.portfolio_id,
        allocation_amount=row.allocation_amount,
        max_notional_usd=row.max_notional_usd,
        max_percent_nlv=row.max_percent_nlv,
        max_orders=row.max_orders,
        allow_short=bool(row.allow_short),
        request=row.request or {},
        orders=row.orders or {},
    )


# ---------------------------------------------------------------------------
# Kill-switch / Resume
# ---------------------------------------------------------------------------


@router.post("/halt")
def halt_trading(db: Session = Depends(get_db)):
    """Emergency kill-switch: set trading_halt=True at runtime and send alert."""
    from app.services.alerting import send_halt_alert

    settings.trading_halt = True
    try:
        _persist_halt(db, True)
    except Exception:
        pass
    send_halt_alert("API /live/halt")
    return {"halted": True, "message": "Trading halted. Call POST /live/resume to re-enable."}


@router.post("/resume")
def resume_trading(db: Session = Depends(get_db)):
    """Resume trading after a halt."""
    from app.services.alerting import send_resume_alert

    if not settings.enable_live_trading:
        raise HTTPException(status_code=403, detail="Live trading is not enabled (ENABLE_LIVE_TRADING=0)")
    settings.trading_halt = False
    try:
        _persist_halt(db, False)
    except Exception:
        pass
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

    # 3. Dry-run mode off
    checks.append({
        "check": "dry_run_disabled",
        "pass": not settings.live_dry_run,
        "detail": "LIVE_DRY_RUN must be false to execute real orders",
    })

    # 4. Market open
    try:
        is_open, reason = market_is_open(settings.market_calendar)
        checks.append({"check": "market_open", "pass": is_open, "detail": reason or ""})
    except Exception as e:
        checks.append({"check": "market_open", "pass": False, "detail": str(e)})

    # 5. IB connection
    try:
        call_ib(lambda ib: True, timeout=5.0)
        checks.append({"check": "ib_connected", "pass": True, "detail": ""})
    except Exception as e:
        checks.append({"check": "ib_connected", "pass": False, "detail": str(e)})

    # 6. Account in IB managed accounts
    try:
        _assert_account_allowed(body.account_id)
        checks.append({"check": "account_whitelisted", "pass": True, "detail": body.account_id})
    except HTTPException as e:
        checks.append({"check": "account_whitelisted", "pass": False, "detail": str(e.detail)})

    # 7. Account NLV within range
    try:
        nlv = _account_nlv(body.account_id)
        nlv_ok = nlv is not None and nlv > 0
        detail = f"NLV=${nlv:,.2f}" if nlv else "could not determine"
        checks.append({"check": "account_nlv_valid", "pass": nlv_ok, "detail": detail})
    except Exception as e:
        checks.append({"check": "account_nlv_valid", "pass": False, "detail": str(e)})

    # 8. Total order value < max % NLV (server-side cap)
    try:
        preview = _build_preview(db, body)
        nlv_val = nlv if nlv else 0
        max_pct = float(settings.live_max_order_pct_nlv)
        total_ok = True
        if nlv_val > 0:
            total_ok = preview.estimated_notional <= nlv_val * max_pct
        detail_msg = f"notional=${preview.estimated_notional:,.2f}, cap={max_pct*100:.0f}% of NLV"
        checks.append({"check": "total_order_within_nlv_cap", "pass": total_ok, "detail": detail_msg})
    except Exception as e:
        checks.append({"check": "total_order_within_nlv_cap", "pass": False, "detail": str(e)})

    # 9. Circuit breaker
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

    # 10. Portfolio concentration check
    try:
        if preview and preview.legs:
            buy_legs = [l for l in preview.legs if l.side == "BUY"]
            if len(buy_legs) >= 2:
                total_buy_notional = sum(abs(l.delta_quantity) * l.price for l in buy_legs)
                max_single = max(abs(l.delta_quantity) * l.price for l in buy_legs)
                concentration = max_single / total_buy_notional if total_buy_notional > 0 else 0
                conc_ok = concentration <= 0.50
                checks.append({
                    "check": "portfolio_concentration",
                    "pass": conc_ok,
                    "detail": f"max single position is {concentration * 100:.0f}% of total buy notional"
                              f" ({len(buy_legs)} tickers)",
                })
            else:
                checks.append({
                    "check": "portfolio_concentration",
                    "pass": True,
                    "detail": f"only {len(buy_legs)} buy ticker(s), skipped",
                })
        else:
            checks.append({"check": "portfolio_concentration", "pass": True, "detail": "no preview legs"})
    except Exception as e:
        checks.append({"check": "portfolio_concentration", "pass": False, "detail": str(e)})

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
            "quantity": _order_qty(leg.delta_quantity),
            "price": float(leg.price),
            "notional": _order_qty(leg.delta_quantity) * float(leg.price),
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


# ---------------------------------------------------------------------------
# Pre-deploy verification engine
# ---------------------------------------------------------------------------


class VerifyFinding(BaseModel):
    code: str
    severity: str  # "error" | "warning" | "info"
    title: str
    detail: str = ""


class VerifyOut(BaseModel):
    ok: bool
    errors: int
    warnings: int
    mode: str
    account_id: str
    portfolio_id: UUID
    allocation_amount: float
    metrics: dict[str, Any]
    findings: list[VerifyFinding]


def _probe_read_only(account_id: str, tickers: Iterable[str]) -> bool | None:
    """Best-effort check whether the IB API rejects order entry (Read-Only mode).

    Sends a whatIf order (placed nowhere — preview only). Returns True if the
    gateway is read-only (IB error 321), False if order entry is accepted, or
    None if it could not be determined.
    """
    syms = [str(t) for t in tickers if str(t).strip()]
    if not syms:
        return None

    def _do(ib: Any) -> bool | None:
        try:
            from ib_insync import MarketOrder, Stock
        except Exception:
            return None
        codes: list[int] = []

        def _on_err(reqId: Any, code: Any, msg: Any, *a: Any) -> None:
            try:
                codes.append(int(code))
            except Exception:
                pass

        ib.errorEvent += _on_err
        try:
            c = Stock(syms[0], "SMART", "USD")
            try:
                ib.qualifyContracts(c)
            except Exception:
                pass
            o = MarketOrder("BUY", 1)
            o.account = account_id
            o.whatIf = True
            st = ib.whatIfOrder(c, o)
            ib.sleep(0.4)
            if 321 in codes:
                return True
            init = getattr(st, "initMarginChange", None)
            if init not in (None, ""):
                return False
            return None
        except Exception:
            # whatIfOrder may raise when the gateway refuses order entry
            return True if 321 in codes else None
        finally:
            try:
                ib.errorEvent -= _on_err
            except Exception:
                pass

    try:
        return call_ib(_do, timeout=15.0)
    except Exception:
        return None


@router.post("/rebalance/verify", response_model=VerifyOut)
def live_rebalance_verify(
    body: LiveRebalanceRequest,
    mode: str = Query(default="live"),
    db: Session = Depends(get_db),
):
    """Pre-deploy verification: simulate the rebalance and report suitability +
    safety findings WITHOUT placing any orders. Does not require live trading."""
    mode = (mode or "live").strip().lower()
    findings: list[VerifyFinding] = []
    metrics: dict[str, Any] = {}
    alloc = float(body.allocation_amount)

    def add(code: str, severity: str, title: str, detail: str = "") -> None:
        findings.append(VerifyFinding(code=code, severity=severity, title=title, detail=detail))

    def result() -> VerifyOut:
        errors = sum(1 for f in findings if f.severity == "error")
        warnings = sum(1 for f in findings if f.severity == "warning")
        return VerifyOut(
            ok=(errors == 0),
            errors=errors,
            warnings=warnings,
            mode=mode,
            account_id=body.account_id,
            portfolio_id=body.portfolio_id,
            allocation_amount=alloc,
            metrics=metrics,
            findings=findings,
        )

    # --- target weights (fetch with shorts allowed so we can analyse everything) ---
    try:
        weights = _build_target_weights(db, body.portfolio_id, alloc, allow_short=True)
    except HTTPException as e:
        add("weights", "error", "Cannot build target weights", str(e.detail))
        return result()

    n_names = len(weights)
    metrics["target_names"] = n_names

    negatives = {t: w for t, w in weights.items() if w < 0}
    if negatives:
        if not body.allow_short:
            add(
                "short_targets",
                "error",
                f"{len(negatives)} short target(s) require a margin account",
                "Enable 'Allow short' (margin account required) or choose a long-only portfolio. e.g. "
                + ", ".join(list(negatives)[:6]),
            )
        else:
            add("short_targets", "warning", f"{len(negatives)} short target(s)", "Shorting uses margin.")

    # --- quotes (paper close when live off, IB quotes when live on) ---
    quotes = _fetch_quotes_for_preview(weights.keys())
    priced = {t for t in weights if t in quotes and quotes[t].price > 0}
    unpriced = sorted(set(weights) - priced)
    metrics["priced"] = len(priced)
    metrics["unpriceable"] = unpriced
    if unpriced:
        shown = ", ".join(unpriced[:15]) + (f" +{len(unpriced) - 15} more" if len(unpriced) > 15 else "")
        add("unpriceable", "warning", f"{len(unpriced)} ticker(s) have no price (likely delisted)", shown)

    # --- sizing / deployment simulation ---
    deployed = 0.0
    dust = 0
    zero_share = 0
    legs = 0
    max_leg_notional = 0.0
    for t, w in weights.items():
        if t not in priced:
            continue
        target_value = alloc * abs(float(w))
        if settings.live_fractional_shares and target_value < float(settings.live_min_leg_usd):
            dust += 1
            continue
        px = float(quotes[t].price)
        qty = _quantize_qty(target_value / px)
        if abs(qty) <= 0:
            zero_share += 1
            continue
        notional = abs(qty) * px
        deployed += notional
        legs += 1
        max_leg_notional = max(max_leg_notional, notional)

    util = (deployed / alloc) if alloc > 0 else 0.0
    metrics.update(
        {
            "legs": legs,
            "deployed": round(deployed, 2),
            "utilization": round(util, 4),
            "dust_skipped": dust,
            "zero_share_dropped": zero_share,
            "max_leg_notional": round(max_leg_notional, 2),
            "fractional": bool(settings.live_fractional_shares),
        }
    )

    # --- suitability findings ---
    if not settings.live_fractional_shares and zero_share > 0:
        sev = "error" if zero_share > n_names * 0.3 else "warning"
        add(
            "whole_share_drop",
            sev,
            f"{zero_share} name(s) round to 0 whole shares",
            "Fractional shares are off, so small-weight names cannot be bought with this cash. "
            "Enable fractional shares or increase the allocation.",
        )

    if priced and util < 0.90:
        sev = "error" if util < 0.5 else "warning"
        add(
            "low_utilization",
            sev,
            f"Only {util * 100:.0f}% of the allocation would deploy",
            f"${deployed:,.0f} of ${alloc:,.0f} invested; the rest stays in cash. "
            f"{dust + zero_share} name(s) are too small for this allocation.",
        )

    if dust > 0:
        add(
            "dust_legs",
            "warning",
            f"{dust} target(s) below ${float(settings.live_min_leg_usd):.0f} were skipped",
            "The portfolio is too granular for this cash; tiny positions are dropped.",
        )

    if n_names > 0:
        per_name = alloc / n_names
        if per_name < float(settings.live_min_leg_usd) * 2:
            add(
                "too_granular",
                "warning",
                f"{n_names} holdings for ${alloc:,.0f} (~${per_name:,.2f} per name)",
                "Use a portfolio with fewer holdings or a larger allocation for faithful tracking.",
            )

    if legs > int(body.max_orders):
        add(
            "order_count",
            "error",
            f"{legs} orders exceed the max_orders limit ({body.max_orders})",
            "Raise max orders or reduce the number of holdings.",
        )

    if deployed > 0 and (max_leg_notional / deployed) > 0.35:
        add(
            "concentration",
            "warning",
            f"Largest position is {max_leg_notional / deployed * 100:.0f}% of deployed capital",
            "High single-name concentration.",
        )

    cheap = sorted([t for t in priced if float(quotes[t].price) < 5.0])
    if cheap:
        add(
            "illiquid",
            "warning",
            f"{len(cheap)} sub-$5 micro-cap name(s)",
            "These may have wide spreads and could be rejected by the live spread check: "
            + ", ".join(cheap[:10]),
        )

    # --- live-mode gating ---
    if mode == "live":
        if not settings.enable_live_trading:
            add(
                "live_disabled",
                "error",
                "Live trading is disabled in the backend (ENABLE_LIVE_TRADING=0)",
                "Set the flag and recreate the API container before deploying live.",
            )
        if settings.live_dry_run:
            add(
                "dry_run",
                "info",
                "Dry-run mode is on (LIVE_DRY_RUN=true)",
                "Execution is blocked; orders are simulated. Turn off to place real orders.",
            )
        if settings.trading_halt:
            add("halted", "error", "Trading is halted", "Resume from the Trade page or clear the halt.")

        try:
            is_open, reason = market_is_open(settings.market_calendar)
            if not is_open:
                add("market_closed", "warning", "The US market is closed", reason or "Live orders fill only during RTH.")
        except Exception as e:  # noqa: BLE001
            add("market_unknown", "warning", "Could not determine market hours", str(e))

        try:
            _assert_account_allowed(body.account_id)
        except HTTPException as e:
            add("account_not_allowed", "error", "Account is not permitted for live trading", str(e.detail))

        try:
            nlv = _account_nlv(body.account_id)
            if nlv is not None and nlv > 0:
                metrics["nlv"] = round(nlv, 2)
                if alloc > nlv:
                    add("alloc_gt_nlv", "error", f"Allocation ${alloc:,.0f} exceeds account NLV ${nlv:,.0f}", "Reduce the allocation.")
                else:
                    cap = float(settings.live_max_order_pct_nlv)
                    if cap > 0 and alloc > nlv * cap:
                        add(
                            "alloc_gt_cap",
                            "warning",
                            f"Allocation is {alloc / nlv * 100:.0f}% of NLV (server cap {cap * 100:.0f}%)",
                            "The rebalance may be rejected by the NLV cap.",
                        )
            else:
                add("nlv_unknown", "warning", "Could not read account NetLiquidation", "")
        except Exception as e:  # noqa: BLE001
            add("nlv_error", "warning", "Could not read account NetLiquidation", str(e))

        read_only = _probe_read_only(body.account_id, sorted(priced))
        if read_only is True:
            add(
                "read_only_api",
                "error",
                "IB Gateway API is in Read-Only mode",
                "Orders are rejected (IB error 321). Disable Read-Only API on the Gateway to trade.",
            )

    return result()
