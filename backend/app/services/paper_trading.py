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


def fetch_last_close_price(ticker: str, *, lookback_days: int = 10) -> PriceQuote:
    """
    Best-effort price lookup using the existing BacktestEngine (yfinance/ib + local cache).
    Raises ValueError if a price cannot be determined.
    """
    t = str(ticker).strip().upper().replace(".", "-")
    if not t:
        raise ValueError("ticker is required")

    # Import from repo root (same approach as portfolio_backtest service).
    from backtest_engine import BacktestEngine  # repo root import

    end = _now_utc()
    start = end - timedelta(days=int(lookback_days))
    be = BacktestEngine(initial_capital=100000.0, price_source="auto")
    data = be.fetch_historical_data([t], start_date=start.strftime("%Y-%m-%d"), end_date=end.strftime("%Y-%m-%d"))
    df = (data or {}).get(t)
    if df is None or df.empty:
        raise ValueError(f"no price data for {t}")
    # Prefer Close; fall back to Adj Close if needed.
    price = None
    for col in ["Close", "Adj Close", "close", "adjclose"]:
        if col in df.columns:
            s = df[col].dropna()
            if not s.empty:
                price = float(s.iloc[-1])
                break
    if price is None or price <= 0:
        raise ValueError(f"invalid price for {t}")

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
    out: dict[str, PriceQuote] = {}
    for t in tickers:
        q = fetch_last_close_price(str(t))
        out[q.ticker] = q
    return out

