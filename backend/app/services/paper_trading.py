from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.paper import PaperAccount, PaperOrder, PaperPosition, PaperTrade


@dataclass(frozen=True)
class PriceQuote:
    ticker: str
    price: float
    as_of: datetime
    source: str


def _now_utc() -> datetime:
    return datetime.utcnow()


def ensure_paper_account(db: Session, account_id: int = 1) -> PaperAccount:
    acct = db.query(PaperAccount).filter(PaperAccount.id == int(account_id)).one_or_none()
    if acct is None:
        acct = PaperAccount(id=int(account_id), name="Default Paper Account", balance=100000.0, currency="USD")
        db.add(acct)
        db.commit()
        db.refresh(acct)
    return acct


def _normalize_ticker(ticker: str) -> str:
    return str(ticker).strip().upper().replace(".", "-")


def _last_close_from_df(df) -> float | None:
    """Extract the most recent valid close from a historical-data DataFrame, or None."""
    if df is None or getattr(df, "empty", True):
        return None
    for col in ["Close", "Adj Close", "close", "adjclose"]:
        if col in df.columns:
            s = df[col].dropna()
            if not s.empty:
                val = s.iloc[-1]
                if hasattr(val, "iloc"):
                    val = val.iloc[0]
                try:
                    price = float(val)
                except (TypeError, ValueError):
                    continue
                if price > 0:
                    return price
    return None


def fetch_last_close_price(ticker: str, *, lookback_days: int = 10) -> PriceQuote:
    """
    Best-effort price lookup using the existing BacktestEngine (yfinance/ib + local cache).
    Raises ValueError if a price cannot be determined.
    """
    t = _normalize_ticker(ticker)
    if not t:
        raise ValueError("ticker is required")

    # Import from repo root (same approach as portfolio_backtest service).
    from backtest_engine import BacktestEngine  # repo root import

    end = _now_utc()
    start = end - timedelta(days=int(lookback_days))
    be = BacktestEngine(initial_capital=100000.0, price_source="auto")
    data = be.fetch_historical_data([t], start_date=start.strftime("%Y-%m-%d"), end_date=end.strftime("%Y-%m-%d"))
    price = _last_close_from_df((data or {}).get(t))
    if price is None:
        raise ValueError(f"no price data for {t}")

    return PriceQuote(ticker=t, price=float(price), as_of=end, source="auto")


def _get_or_create_position(db: Session, account_id: int, ticker: str, currency: str = "USD") -> PaperPosition:
    pos = (
        db.query(PaperPosition)
        .filter(PaperPosition.account_id == int(account_id), PaperPosition.ticker == str(ticker))
        .one_or_none()
    )
    if pos is None:
        pos = PaperPosition(
            account_id=int(account_id),
            ticker=str(ticker),
            quantity=0.0,
            avg_cost=0.0,
            currency=currency,
            strategy=None,
        )
        db.add(pos)
        db.flush()
    return pos


def place_market_order(
    db: Session,
    *,
    account_id: int,
    ticker: str,
    side: str,
    quantity: float,
    price: float | None = None,
    notes: str | None = None,
    strategy: str | None = None,
) -> tuple[PaperOrder, PaperTrade, PaperAccount, PaperPosition]:
    """
    Paper market order with immediate fill.
    - Updates cash + position atomically (within the caller's transaction).
    - Creates PaperOrder and PaperTrade rows.
    """
    acct = ensure_paper_account(db, int(account_id))

    t = str(ticker).strip().upper().replace(".", "-")
    s = str(side).strip().upper()
    qty = float(quantity)
    if not t:
        raise ValueError("ticker is required")
    if s not in {"BUY", "SELL"}:
        raise ValueError("side must be BUY or SELL")
    if qty <= 0:
        raise ValueError("quantity must be > 0")

    if price is None:
        quote = fetch_last_close_price(t)
        fill_price = float(quote.price)
    else:
        fill_price = float(price)
        if fill_price <= 0:
            raise ValueError("price must be > 0")

    value = float(qty * fill_price)
    pos = _get_or_create_position(db, int(account_id), t, currency=acct.currency)

    # Apply cash/position changes.
    if s == "BUY":
        if float(acct.balance) + 1e-9 < value:
            raise ValueError("insufficient cash")
        old_qty = float(pos.quantity)
        old_cost = float(pos.avg_cost)
        new_qty = old_qty + qty
        new_avg = ((old_qty * old_cost) + (qty * fill_price)) / new_qty if new_qty > 0 else 0.0
        pos.quantity = float(new_qty)
        pos.avg_cost = float(new_avg)
        pos.strategy = strategy or pos.strategy
        acct.balance = float(acct.balance) - value
    else:  # SELL
        old_qty = float(pos.quantity)
        if old_qty + 1e-9 < qty:
            raise ValueError("insufficient position to sell")
        new_qty = old_qty - qty
        pos.quantity = float(new_qty)
        if new_qty <= 1e-12:
            pos.avg_cost = 0.0
        acct.balance = float(acct.balance) + value

    # Create order + trade.
    now = _now_utc()
    order = PaperOrder(
        account_id=int(account_id),
        ticker=t,
        action=s,
        quantity=float(qty),
        order_type="MKT",
        status="FILLED",
        created_at=now,
        submitted_at=now,
        filled_at=now,
        fill_price=float(fill_price),
        value=float(value),
        notes=notes,
        raw={},
    )
    db.add(order)
    db.flush()  # get order.id

    trade = PaperTrade(
        account_id=int(account_id),
        order_id=order.id,
        timestamp=now,
        ticker=t,
        action=s,
        quantity=float(qty),
        price=float(fill_price),
        value=float(value),
        strategy=strategy,
        notes=notes,
    )
    db.add(trade)
    db.flush()

    return order, trade, acct, pos


def fetch_prices(tickers: Iterable[str]) -> dict[str, PriceQuote]:
    """
    Batched best-effort price lookup. Fetches all tickers in a single
    BacktestEngine.fetch_historical_data call (avoids the per-ticker request
    burst that intermittently rate-limited the source and silently dropped
    names), then falls back to an individual lookup only for genuine misses.

    The result is keyed by BOTH the original ticker string and its normalized
    form so callers can look up by whichever they hold.
    """
    raw = [str(t) for t in tickers if str(t).strip()]
    norm_of = {t: _normalize_ticker(t) for t in raw}
    uniq = sorted({n for n in norm_of.values() if n})
    out: dict[str, PriceQuote] = {}
    if not uniq:
        return out

    from backtest_engine import BacktestEngine  # repo root import

    end = _now_utc()
    start = end - timedelta(days=10)

    prices: dict[str, float] = {}
    try:
        be = BacktestEngine(initial_capital=100000.0, price_source="auto")
        data = be.fetch_historical_data(
            uniq, start_date=start.strftime("%Y-%m-%d"), end_date=end.strftime("%Y-%m-%d")
        ) or {}
        for n in uniq:
            p = _last_close_from_df(data.get(n))
            if p is not None:
                prices[n] = p
    except Exception:
        # batch failed entirely — fall through to per-ticker fallback below
        pass

    # Fallback only for tickers the batch did not resolve.
    for n in uniq:
        if n in prices:
            continue
        try:
            prices[n] = fetch_last_close_price(n).price
        except Exception:
            pass

    for t in raw:
        n = norm_of.get(t)
        if not n or n not in prices:
            continue
        out[t] = PriceQuote(ticker=t, price=prices[n], as_of=end, source="auto")
        out[n] = PriceQuote(ticker=n, price=prices[n], as_of=end, source="auto")
    return out

