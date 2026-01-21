from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Literal, Tuple

import pandas as pd

from app.core.config import settings
from app.services.portfolio_math import nav_blend_equity_curves
from app.services.serialization import equity_curve_to_records


PortfolioMode = Literal["holdings_union", "nav_blend"]


def _parse_dt(s: str) -> datetime:
    return pd.to_datetime(s).to_pydatetime()


def run_strategy_backtest(strategy_name: str, start_date: str, end_date: str, transaction_cost_bps: float = 0.0) -> dict:
    """
    Thin wrapper around the existing rebalancing engine in the repo root.
    This runs an actual strategy replication backtest (may hit Quiver API + price source).
    """
    if not settings.quiver_api_key:
        return {"error": "QUIVER_API_KEY not configured"}

    from rebalancing_backtest_engine import RebalancingBacktestEngine  # repo root import

    bt = RebalancingBacktestEngine(
        quiver_api_key=settings.quiver_api_key,
        initial_capital=100000.0,
        transaction_cost_bps=float(transaction_cost_bps),
        price_source=settings.price_source,
    )
    return bt.run_rebalancing_backtest(
        strategy_name=strategy_name,
        start_date=_parse_dt(start_date),
        end_date=_parse_dt(end_date),
    )


def portfolio_backtest_nav_blend(
    strategy_names: list[str],
    strategy_weights: Dict[str, float],
    start_date: str,
    end_date: str,
    transaction_cost_bps: float = 0.0,
) -> dict:
    """
    NAV blend: run each strategy separately and blend their equity curves by weights.
    """
    results: dict[str, dict] = {}
    curves: dict[str, pd.Series] = {}

    for name in strategy_names:
        res = run_strategy_backtest(name, start_date, end_date, transaction_cost_bps=transaction_cost_bps)
        results[name] = res
        if "error" in res:
            continue
        curve_records = equity_curve_to_records(res.get("equity_curve"))
        s = pd.Series(
            [r["value"] for r in curve_records],
            index=pd.to_datetime([r["date"] for r in curve_records], errors="coerce"),
            dtype="float64",
        ).dropna()
        s = s[~s.index.duplicated(keep="last")].sort_index()
        if not s.empty:
            curves[name] = s

    blended = nav_blend_equity_curves(curves, strategy_weights)
    if blended.empty:
        return {"error": "No equity curves available to blend", "strategy_results": results}

    # Basic portfolio metrics from blended series
    daily = blended.pct_change().dropna()
    total_return = float(blended.iloc[-1] / blended.iloc[0] - 1.0)
    n_days = int(len(daily))
    years = n_days / 252.0 if n_days > 0 else 0.0
    cagr = float((1.0 + total_return) ** (1.0 / years) - 1.0) if years > 0 else 0.0
    vol = float(daily.std() * (252.0**0.5)) if n_days > 1 else 0.0
    sharpe = float((daily.mean() * 252.0) / (daily.std() * (252.0**0.5))) if n_days > 1 and daily.std() > 0 else 0.0
    roll_max = blended.cummax()
    dd = (blended / roll_max) - 1.0
    max_dd = float(dd.min()) if not dd.empty else 0.0

    equity_records = [{"date": str(pd.Timestamp(idx).date()), "value": float(val)} for idx, val in blended.items()]

    return {
        "mode": "nav_blend",
        "start_date": start_date,
        "end_date": end_date,
        "portfolio": {
            "total_return": total_return,
            "cagr": cagr,
            "volatility": vol,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "n_days": n_days,
            "final_value": float(blended.iloc[-1]),
        },
        "equity_curve": equity_records,
        "strategy_results": results,
    }


def portfolio_backtest_holdings_union(*args, **kwargs) -> dict:
    """
    holdings_union (per-strategy rebalance schedule):
    - Each strategy has its own rebalance event dates and target weights.
    - The portfolio's effective holdings on any date are the weighted sum of each
      strategy's *current* holdings (last rebalance <= date).
    - We build a merged event calendar (union of strategy rebalance dates) and
      backtest the combined weights.
    """
    strategy_names: list[str] = kwargs["strategy_names"]
    strategy_weights: dict[str, float] = kwargs["strategy_weights"]
    start_date: str = kwargs["start_date"]
    end_date: str = kwargs["end_date"]
    transaction_cost_bps: float = float(kwargs.get("transaction_cost_bps") or 0.0)

    if not settings.quiver_api_key:
        return {"error": "QUIVER_API_KEY not configured"}

    from rebalancing_backtest_engine import RebalancingBacktestEngine, RebalanceEvent  # repo root

    bt = RebalancingBacktestEngine(
        quiver_api_key=settings.quiver_api_key,
        initial_capital=100000.0,
        transaction_cost_bps=float(transaction_cost_bps),
        price_source=settings.price_source,
    )

    start = _parse_dt(start_date)
    end = _parse_dt(end_date)
    if end <= start:
        return {"error": "end_date must be after start_date"}

    # Build per-strategy event lists
    per: dict[str, list[RebalanceEvent]] = {}
    all_dates: set[pd.Timestamp] = {pd.Timestamp(start)}
    for name in strategy_names:
        w = float(strategy_weights.get(name, 0.0))
        if w <= 0:
            continue
        evs = bt._generate_rebalance_events(strategy_name=name, start=start, end=end, lookback_days_override=None)
        if not evs:
            continue
        per[name] = evs
        for ev in evs:
            all_dates.add(pd.Timestamp(ev.date))

    merged_dates = sorted({d.normalize() for d in all_dates})
    if not merged_dates:
        return {"error": "No rebalance events generated"}

    # For each strategy, keep a cursor to current weights as we move forward in time.
    cursors = {name: 0 for name in per.keys()}
    current_weights: dict[str, dict[str, float]] = {}

    merged_events: list[RebalanceEvent] = []
    for d in merged_dates:
        dt = pd.Timestamp(d).to_pydatetime()
        combined: dict[str, float] = {}

        for name, evs in per.items():
            # advance cursor while next event <= dt
            i = cursors[name]
            while i + 1 < len(evs) and evs[i + 1].date <= dt:
                i += 1
            cursors[name] = i
            w_strat = float(strategy_weights.get(name, 0.0))
            if w_strat <= 0:
                continue
            wmap = evs[i].weights or {}
            for t, w in wmap.items():
                combined[t] = combined.get(t, 0.0) + (w_strat * float(w))

        combined = bt._clean_weight_map(combined)
        merged_events.append(RebalanceEvent(date=dt, weights=combined))

    # Now simulate combined events using the same logic as run_rebalancing_backtest.
    # Prefetch prices for all tickers over full horizon.
    all_tickers: list[str] = sorted({t for ev in merged_events for t in ev.weights.keys()})
    if not all_tickers:
        return {"error": "No tickers found for portfolio over this period"}

    # `start` is a python datetime; subtracting a pandas Timedelta returns a python datetime
    # (which doesn't have `.to_pydatetime()`), so normalize via Timestamp.
    prefetch_start = (pd.Timestamp(start) - pd.Timedelta(days=7)).to_pydatetime()
    price_data = bt.pricer.fetch_historical_data(
        tickers=all_tickers,
        start_date=pd.Timestamp(prefetch_start).strftime("%Y-%m-%d"),
        end_date=pd.Timestamp(end).strftime("%Y-%m-%d"),
    )
    if not price_data:
        return {"error": "No historical price data available"}

    sample_df = next(iter(price_data.values()))
    prefetched_index = sample_df.index
    prefetched_closes: dict[str, pd.Series] = {}
    prices_full = pd.DataFrame(index=prefetched_index)
    for t, df in price_data.items():
        s = bt.pricer._extract_series(df, "Close", t)
        if s.empty:
            continue
        s = s.reindex(prefetched_index).ffill()
        prefetched_closes[t] = s
        prices_full[t] = s
    prices_full = prices_full.sort_index().ffill()
    returns_full = prices_full.pct_change()

    portfolio_value = bt.initial_capital
    equity_dates: list[pd.Timestamp] = []
    equity_values: list[float] = []
    daily_portfolio_returns: list[float] = []

    prev_weights: dict[str, float] = {}
    for i, ev in enumerate(merged_events):
        seg_start = ev.date
        seg_end = merged_events[i + 1].date if i + 1 < len(merged_events) else end

        raw_weights = ev.weights if ev.weights else prev_weights
        if not raw_weights:
            continue

        mask = bt._date_range_mask(returns_full.index, seg_start, seg_end)
        seg_returns = returns_full.loc[mask]
        if seg_returns.empty:
            continue

        if bt.transaction_cost_bps > 0:
            turnover = bt._compute_turnover(prev_weights, raw_weights)
            cost = (bt.transaction_cost_bps / 10000.0) * turnover
            portfolio_value *= max(0.0, 1.0 - cost)

        prev_weights = raw_weights

        tickers_in_segment = [t for t in seg_returns.columns if t in raw_weights]
        if not tickers_in_segment:
            continue

        # Preserve gross exposures from raw weights (important for long-short blends).
        pos_sum = sum(v for v in raw_weights.values() if v > 0)
        neg_sum = sum(abs(v) for v in raw_weights.values() if v < 0)
        has_shorts = neg_sum > 0
        long_target = pos_sum if has_shorts else None
        short_target = neg_sum if has_shorts else None

        weights = bt._normalize_weights_for_available_tickers(
            weights=raw_weights,
            available_tickers=tickers_in_segment,
            long_target=long_target,
            short_target=short_target,
        )
        if not weights:
            continue

        w_vec = pd.Series({t: weights.get(t, 0.0) for t in tickers_in_segment}, dtype="float64").to_numpy()

        for dt, row in seg_returns[tickers_in_segment].iterrows():
            r = row.to_numpy(dtype="float64")
            if pd.isna(r).any():
                ok = ~pd.isna(r)
                todays = [t for t, okb in zip(tickers_in_segment, ok) if okb]
                if not todays:
                    continue
                day_weights = bt._normalize_weights_for_available_tickers(
                    weights=raw_weights,
                    available_tickers=todays,
                    long_target=long_target,
                    short_target=short_target,
                )
                w_day = pd.Series([day_weights.get(t, 0.0) for t in todays], dtype="float64").to_numpy()
                r_day = r[ok]
                port_r = float((w_day * r_day).sum())
            else:
                port_r = float((w_vec * r).sum())

            portfolio_value *= (1.0 + port_r)
            equity_dates.append(dt)
            equity_values.append(portfolio_value)
            daily_portfolio_returns.append(port_r)

    if len(equity_values) < 2:
        return {"error": "Insufficient overlapping price data for portfolio backtest"}

    blended = pd.Series(equity_values, index=pd.DatetimeIndex(equity_dates, name="date"), dtype="float64").sort_index()
    daily = blended.pct_change().dropna()
    total_return = float(blended.iloc[-1] / blended.iloc[0] - 1.0)
    n_days = int(len(daily))
    years = n_days / 252.0 if n_days > 0 else 0.0
    cagr = float((1.0 + total_return) ** (1.0 / years) - 1.0) if years > 0 else 0.0
    vol = float(daily.std() * (252.0**0.5)) if n_days > 1 else 0.0
    sharpe = float((daily.mean() * 252.0) / (daily.std() * (252.0**0.5))) if n_days > 1 and daily.std() > 0 else 0.0
    roll_max = blended.cummax()
    dd = (blended / roll_max) - 1.0
    max_dd = float(dd.min()) if not dd.empty else 0.0

    equity_records = [{"date": str(pd.Timestamp(idx).date()), "value": float(val)} for idx, val in blended.items()]

    return {
        "mode": "holdings_union",
        "start_date": start_date,
        "end_date": end_date,
        "portfolio": {
            "total_return": total_return,
            "cagr": cagr,
            "volatility": vol,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "n_days": n_days,
            "final_value": float(blended.iloc[-1]),
        },
        "equity_curve": equity_records,
        "strategy_results": {},
    }
