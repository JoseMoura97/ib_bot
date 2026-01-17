"""
Rebalancing Backtest Engine

Runs time-series strategy replication with:
- Rolling lookback windows (no lookahead bias)
- Scheduled rebalancing (weekly/monthly/quarterly)
- Optional transaction costs
- Support for long-short weights (negative weights)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from backtest_engine import BacktestEngine
from quiver_engine import QuiverStrategyEngine
from quiver_strategy_rules import QuiverStrategyRules
from strategy_replicator import StrategyReplicator
from metrics_utils import period_return_from_equity, regression_vs_benchmark, win_loss_stats


@dataclass(frozen=True)
class RebalanceEvent:
    date: datetime
    weights: Dict[str, float]  # ticker -> weight (may be negative)


class RebalancingBacktestEngine:
    """
    Backtest engine that matches Quiver-style methodology:
    recompute holdings/weights on a rebalance schedule, and apply those weights
    to daily returns until the next rebalance.
    """

    def __init__(
        self,
        quiver_api_key: str,
        initial_capital: float = 100000.0,
        transaction_cost_bps: float = 0.0,
        price_source: Optional[str] = None,
    ):
        """
        Args:
            quiver_api_key: Quiver API key
            initial_capital: starting portfolio value
            transaction_cost_bps: cost applied on each rebalance based on turnover.
                Example: 10 bps = 0.10% per unit turnover.
        """
        self.initial_capital = float(initial_capital)
        self.transaction_cost_bps = float(transaction_cost_bps)

        self.quiver = QuiverStrategyEngine(quiver_api_key)
        self.replicator = StrategyReplicator(initial_capital=self.initial_capital)
        # price_source: 'yfinance' (default), 'ib', or 'auto'
        src = (price_source or os.getenv("PRICE_SOURCE", "yfinance")).lower().strip()
        self.pricer = BacktestEngine(initial_capital=self.initial_capital, price_source=src)

    @staticmethod
    def _to_datetime(d: str | datetime) -> datetime:
        if isinstance(d, datetime):
            return d
        return pd.to_datetime(d).to_pydatetime()

    @staticmethod
    def _date_range_mask(index: pd.DatetimeIndex, start: datetime, end: datetime) -> pd.Series:
        # inclusive start, exclusive end (end is next rebalance)
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        return (index >= start_ts) & (index < end_ts)

    @staticmethod
    def _normalize_weights_for_available_tickers(
        weights: Dict[str, float],
        available_tickers: List[str],
        long_target: Optional[float] = None,
        short_target: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Normalize weights to account for missing tickers (delisted/unpriced).

        - Long-only: weights re-normalized to sum to 1.0 across available tickers.
        - Long-short: long and short legs re-normalized separately to match targets
          (default targets = original exposures if not provided).
        """
        if not weights:
            return {}

        w = {t: float(weights.get(t, 0.0)) for t in available_tickers if t in weights}
        if not w:
            return {}

        has_shorts = any(v < 0 for v in w.values())
        if not has_shorts:
            total = sum(v for v in w.values() if v > 0)
            if total <= 0:
                return {}
            return {t: (v / total) for t, v in w.items() if v > 0}

        pos = {t: v for t, v in w.items() if v > 0}
        neg = {t: v for t, v in w.items() if v < 0}

        pos_sum = sum(pos.values())
        neg_sum = sum(abs(v) for v in neg.values())

        # Default targets preserve the intended gross exposure from the original weights
        if long_target is None:
            long_target = pos_sum
        if short_target is None:
            short_target = neg_sum

        scaled: Dict[str, float] = {}

        if pos and pos_sum > 0 and long_target is not None:
            scale = float(long_target) / pos_sum
            for t, v in pos.items():
                scaled[t] = v * scale

        if neg and neg_sum > 0 and short_target is not None:
            scale = float(short_target) / neg_sum
            for t, v in neg.items():
                scaled[t] = v * scale  # v is negative already

        return scaled

    def _compute_turnover(self, prev: Dict[str, float], nxt: Dict[str, float]) -> float:
        """Simple turnover estimate: sum of absolute weight changes."""
        if not prev:
            return sum(abs(v) for v in nxt.values())
        tickers = set(prev) | set(nxt)
        return float(sum(abs(nxt.get(t, 0.0) - prev.get(t, 0.0)) for t in tickers))

    def _clean_weight_map(self, weights: Dict[str, float]) -> Dict[str, float]:
        """
        Clean/normalize ticker symbols in a weight map to be compatible with yfinance:
        - remove '$'
        - upper-case
        - convert '.' -> '-' (e.g. BRK.B -> BRK-B)
        - drop obviously invalid tickers

        Aggregates weights that collapse to the same cleaned ticker.
        """
        if not weights:
            return {}
        cleaned = {}
        valid = set(self.pricer._clean_tickers(list(weights.keys())))
        for raw_ticker, w in weights.items():
            if not isinstance(raw_ticker, str):
                continue
            t = raw_ticker.replace("$", "").strip().upper().replace(".", "-")
            if t not in valid:
                continue
            # Heuristics to drop obvious non-ticker identifiers (CUSIPs, headers, placeholders)
            if t in {"SYMBOL", "TICKER", "CUSIP"}:
                continue
            if len(t) > 7:
                continue
            if not any(ch.isalpha() for ch in t):
                continue
            cleaned[t] = cleaned.get(t, 0.0) + float(w)
        # Drop near-zero weights after aggregation
        cleaned = {t: w for t, w in cleaned.items() if abs(w) > 1e-12}
        return cleaned

    def _generate_rebalance_events(
        self,
        strategy_name: str,
        start: datetime,
        end: datetime,
        lookback_days_override: Optional[int] = None,
    ) -> List[RebalanceEvent]:
        rules = QuiverStrategyRules.get_strategy_rules(strategy_name)
        cfg = self.replicator.get_strategy_config(strategy_name)

        lookback_days = int(
            lookback_days_override
            if lookback_days_override is not None
            else (cfg.get("lookback_days") or rules.get("lookback_days") or 90)
        )

        # For event-driven (on_trade) strategies, rebalance only when new trades occur
        # instead of approximating with daily checks.
        if rules.get("rebalance_frequency") == "on_trade":
            # Pull all available history up to `end` and use distinct transaction dates.
            full_lookback = max(lookback_days, int((end - start).days) + 30)
            raw_full = self.quiver._get_raw_data_with_metadata_at_date(
                strategy_name=strategy_name,
                as_of_date=end,
                lookback_days=full_lookback,
            )
            date_col = None
            for c in ["TransactionDate", "ReportDate", "Date", "LastUpdate"]:
                if c in raw_full.columns:
                    date_col = c
                    break
            if date_col is not None and not raw_full.empty:
                if not pd.api.types.is_datetime64_any_dtype(raw_full[date_col]):
                    raw_full[date_col] = pd.to_datetime(raw_full[date_col], errors="coerce")
                dts = (
                    raw_full.dropna(subset=[date_col])
                    .loc[(raw_full[date_col] >= start) & (raw_full[date_col] <= end), date_col]
                    .dt.normalize()
                    .drop_duplicates()
                    .sort_values()
                    .tolist()
                )
                scheduled = [pd.Timestamp(d).to_pydatetime() for d in dts]
            else:
                scheduled = []
        else:
            scheduled = QuiverStrategyRules.get_rebalance_dates(strategy_name, start, end)

        # Ensure we always have a rebalance at the start date.
        dates = sorted({start, *scheduled})

        events: List[RebalanceEvent] = []
        prog = _ProgressBar(total=len(dates), prefix=f"{strategy_name} | events")
        for d in dates:
            raw = self.quiver._get_raw_data_with_metadata_at_date(
                strategy_name=strategy_name,
                as_of_date=d,
                lookback_days=lookback_days,
            )

            weights = self.replicator.apply_strategy_weights_at_date(
                raw_data=raw,
                strategy_name=strategy_name,
                as_of_date=d,
                lookback_days=lookback_days,
            )

            weights = self._clean_weight_map(weights)
            events.append(RebalanceEvent(date=d, weights=weights))
            prog.step(extra=f"{pd.Timestamp(d).date()} (n={len(weights)})")

        return events

    def run_rebalancing_backtest(
        self,
        strategy_name: str,
        start_date: str | datetime,
        end_date: str | datetime,
        lookback_days_override: Optional[int] = None,
    ) -> Dict:
        start = self._to_datetime(start_date)
        end = self._to_datetime(end_date)
        if end <= start:
            return {"error": "end_date must be after start_date"}

        events = self._generate_rebalance_events(
            strategy_name=strategy_name,
            start=start,
            end=end,
            lookback_days_override=lookback_days_override,
        )
        if not events:
            return {"error": "No rebalance events generated"}

        rules = QuiverStrategyRules.get_strategy_rules(strategy_name)
        precomputed_returns: Optional[pd.DataFrame] = None
        prefetched_index: Optional[pd.Index] = None
        prefetched_closes: Dict[str, pd.Series] = {}

        # Prefetch prices once per strategy (batched inside the pricer), then slice per segment.
        # This avoids hundreds/thousands of small per-segment downloads (especially painful for IB and yfinance).
        #
        # For small universes we also build a full returns matrix once, for speed.
        max_prefetch_full_matrix = int(os.getenv("MAX_PREFETCH_TICKERS", "250"))
        all_tickers_all_events: List[str] = []
        for ev in events:
            all_tickers_all_events.extend(list(ev.weights.keys()))
        all_tickers_all_events = sorted(set(all_tickers_all_events))

        if not all_tickers_all_events:
            return {"error": "No tickers found for strategy over this period"}

        # Pull a few extra days before start so pct_change has a prior close.
        prefetch_start = (start - timedelta(days=7))
        fetch_prog = _ProgressBar(total=100, prefix=f"{strategy_name} | prices")
        price_data = self.pricer.fetch_historical_data(
            tickers=all_tickers_all_events,
            start_date=prefetch_start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
            progress_callback=fetch_prog.callback(),
        )
        if not price_data:
            return {"error": "No historical price data available"}

        sample_df = next(iter(price_data.values()))
        prefetched_index = sample_df.index
        prices_full: Optional[pd.DataFrame] = None
        if len(all_tickers_all_events) <= max_prefetch_full_matrix:
            prices_full = pd.DataFrame(index=prefetched_index)

        for t, df in price_data.items():
            s = self.pricer._extract_series(df, "Close", t)
            if s.empty:
                continue
            s = s.reindex(prefetched_index).ffill()
            prefetched_closes[t] = s
            if prices_full is not None:
                prices_full[t] = s

        if prices_full is not None and not prices_full.empty:
            prices_full = prices_full.sort_index().ffill()
            precomputed_returns = prices_full.pct_change()

        portfolio_value = self.initial_capital
        equity_dates: List[pd.Timestamp] = []
        equity_values: List[float] = []
        daily_portfolio_returns: List[float] = []

        prev_weights: Dict[str, float] = {}

        # Walk each rebalance segment.
        seg_prog = _ProgressBar(total=max(1, len(events)), prefix=f"{strategy_name} | segments")
        for i, ev in enumerate(events):
            seg_start = ev.date
            seg_end = events[i + 1].date if i + 1 < len(events) else end

            # If we got no weights for this rebalance, carry the previous portfolio.
            raw_weights = ev.weights if ev.weights else prev_weights
            if not raw_weights:
                continue

            if precomputed_returns is not None:
                returns = precomputed_returns
            elif prefetched_index is not None and prefetched_closes:
                # Slice the prefetched price series for just this segment's window and tickers.
                seg_fetch_start = (seg_start - timedelta(days=7))
                idx_mask = self._date_range_mask(prefetched_index, seg_fetch_start, seg_end)
                seg_idx = prefetched_index[idx_mask]
                if len(seg_idx) == 0:
                    continue

                prices = pd.DataFrame(index=seg_idx)
                for t in raw_weights.keys():
                    s = prefetched_closes.get(t)
                    if s is not None:
                        prices[t] = s.loc[seg_idx]
                if prices.empty:
                    seg_prog.step(extra=f"{i+1}/{len(events)} (no prices)")
                    continue
                prices = prices.sort_index().ffill()
                returns = prices.pct_change()
            else:
                # Fetch only the tickers we need for this segment.
                # Pull a few extra days before seg_start so pct_change has a prior close.
                fetch_start = (seg_start - timedelta(days=7))
                fetch_prog = _ProgressBar(total=100, prefix=f"{strategy_name} | prices")
                price_data = self.pricer.fetch_historical_data(
                    tickers=list(raw_weights.keys()),
                    start_date=fetch_start.strftime("%Y-%m-%d"),
                    end_date=seg_end.strftime("%Y-%m-%d"),
                    progress_callback=fetch_prog.callback(),
                )
                if not price_data:
                    seg_prog.step(extra=f"{i+1}/{len(events)} (no prices)")
                    continue

                # Build price matrix for this segment.
                sample_df = next(iter(price_data.values()))
                prices = pd.DataFrame(index=sample_df.index)
                for t, df in price_data.items():
                    s = self.pricer._extract_series(df, "Close", t)
                    if not s.empty:
                        prices[t] = s
                prices = prices.sort_index().ffill()
                returns = prices.pct_change()

            # Determine availability in this segment.
            mask = self._date_range_mask(returns.index, seg_start, seg_end)
            seg_returns = returns.loc[mask]
            if seg_returns.empty:
                continue

            # Turnover + transaction cost on rebalance day
            if self.transaction_cost_bps > 0:
                turnover = self._compute_turnover(prev_weights, raw_weights)
                cost = (self.transaction_cost_bps / 10000.0) * turnover
                portfolio_value *= max(0.0, 1.0 - cost)

            prev_weights = raw_weights

            # For long-short strategies, preserve intended leg exposures.
            cfg = self.replicator.get_strategy_config(strategy_name)
            is_long_short = cfg.get("type") == "long_short" or any(v < 0 for v in raw_weights.values())
            long_target = cfg.get("long_weight", 1.30) if is_long_short else None
            short_target = cfg.get("short_weight", 0.30) if is_long_short else None

            tickers_in_segment = [t for t in seg_returns.columns if t in raw_weights]
            if not tickers_in_segment:
                continue

            weights = self._normalize_weights_for_available_tickers(
                weights=raw_weights,
                available_tickers=tickers_in_segment,
                long_target=long_target,
                short_target=short_target,
            )
            if not weights:
                continue

            w_vec = np.array([weights.get(t, 0.0) for t in tickers_in_segment], dtype=float)

            for dt, row in seg_returns[tickers_in_segment].iterrows():
                r = row.to_numpy(dtype=float)

                # If any returns are NaN today, re-normalize weights for the day.
                ok_mask = ~np.isnan(r)
                if not np.all(ok_mask):
                    todays = [t for t, ok in zip(tickers_in_segment, ok_mask) if ok]
                    if not todays:
                        continue
                    day_weights = self._normalize_weights_for_available_tickers(
                        weights=raw_weights,
                        available_tickers=todays,
                        long_target=long_target,
                        short_target=short_target,
                    )
                    w_day = np.array([day_weights.get(t, 0.0) for t in todays], dtype=float)
                    r_day = r[ok_mask]
                    port_r = float(np.dot(w_day, r_day))
                else:
                    port_r = float(np.dot(w_vec, r))

                portfolio_value *= (1.0 + port_r)
                equity_dates.append(dt)
                equity_values.append(portfolio_value)
                daily_portfolio_returns.append(port_r)

            seg_prog.step(extra=f"{i+1}/{len(events)} {pd.Timestamp(seg_start).date()}->{pd.Timestamp(seg_end).date()}")

        if len(equity_values) < 2:
            return {"error": "Insufficient overlapping price data for rebalancing backtest"}

        daily_returns = np.array(daily_portfolio_returns, dtype=float)
        # Use actual elapsed time for CAGR to avoid inflating results when some days are skipped
        first_dt = pd.to_datetime(equity_dates[0])
        last_dt = pd.to_datetime(equity_dates[-1])
        elapsed_days = max(1, int((last_dt - first_dt).days))
        n_years = elapsed_days / 365.25
        total_return = (equity_values[-1] / self.initial_capital) - 1.0
        cagr = (equity_values[-1] / self.initial_capital) ** (1.0 / n_years) - 1.0 if n_years > 0 else 0.0
        volatility = float(np.std(daily_returns) * np.sqrt(252.0))
        sharpe_ratio = (cagr - 0.02) / volatility if volatility > 0 else 0.0

        equity_arr = np.array(equity_values, dtype=float)
        peak = np.maximum.accumulate(equity_arr)
        drawdown = (equity_arr - peak) / peak
        max_drawdown = float(np.min(drawdown))

        equity_curve = pd.DataFrame(
            {"portfolio_value": equity_values},
            index=pd.DatetimeIndex(equity_dates, name="date"),
        )

        # ---- Additional metrics (with SPY benchmark) ----
        returns_index = pd.DatetimeIndex(equity_dates)
        returns_series = pd.Series(daily_returns, index=returns_index).sort_index()

        # Win/loss stats
        win_rate, avg_win, avg_loss = win_loss_stats(daily_returns)
        std_dev = float(np.std(daily_returns) * np.sqrt(252.0))

        # Trades (approx): count of weight changes at each rebalance
        trades = 0
        eps = 1e-9
        prev_w: Dict[str, float] = {}
        for ev in events:
            nxt = ev.weights or prev_w
            if not nxt:
                continue
            tickers = set(prev_w) | set(nxt)
            trades += sum(1 for t in tickers if abs(nxt.get(t, 0.0) - prev_w.get(t, 0.0)) > eps)
            prev_w = dict(nxt)

        ret_1d = period_return_from_equity(equity_curve, 1)
        ret_30d = period_return_from_equity(equity_curve, 30)
        ret_1y = period_return_from_equity(equity_curve, 365)

        # Benchmark (SPY) regression stats
        beta = None
        alpha = None
        info_ratio = None
        treynor = None
        bench_ret_1d = None
        bench_ret_30d = None
        bench_ret_1y = None
        try:
            bench_start = (pd.Timestamp(start) - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
            bench_end = pd.Timestamp(end).strftime("%Y-%m-%d")
            bench_data = self.pricer.fetch_historical_data(["SPY"], start_date=bench_start, end_date=bench_end)
            if bench_data and "SPY" in bench_data:
                bclose = self.pricer._extract_series(bench_data["SPY"], "Close", "SPY").sort_index()
                bret = bclose.pct_change().dropna()

                # Period returns for SPY
                if len(bclose) >= 2:
                    bench_ret_1d = float(bclose.iloc[-1] / bclose.iloc[-2] - 1.0)
                # 30d/1y based on calendar lookback, using last available <= target
                def _bench_period(days_back: int) -> Optional[float]:
                    if bclose.empty:
                        return None
                    last_dt = bclose.index.max()
                    target = pd.Timestamp(last_dt) - pd.Timedelta(days=int(days_back))
                    hist = bclose.loc[:target]
                    if hist.empty:
                        return None
                    v1 = float(bclose.iloc[-1])
                    v0 = float(hist.iloc[-1])
                    return (v1 / v0) - 1.0 if v0 != 0 else None

                bench_ret_30d = _bench_period(30)
                bench_ret_1y = _bench_period(365)

                stats = regression_vs_benchmark(returns_series, bret, rf_annual=0.02)
                beta = stats.beta
                alpha = stats.alpha_annual
                info_ratio = stats.info_ratio
                treynor = stats.treynor
        except Exception:
            pass

        return {
            "strategy": strategy_name,
            "start_date": str(pd.Timestamp(start).date()),
            "end_date": str(pd.Timestamp(end).date()),
            "initial_capital": self.initial_capital,
            "final_value": float(equity_values[-1]),
            "total_return": float(total_return),
            "cagr": float(cagr),
            "volatility": float(volatility),
            "std_dev": float(std_dev),
            "sharpe_ratio": float(sharpe_ratio),
            "max_drawdown": max_drawdown,
            "n_days": int(len(daily_returns)),
            "trades": int(trades),
            "win_rate": float(win_rate),
            "avg_win": float(avg_win),
            "avg_loss": float(avg_loss),
            "return_1d": float(ret_1d) if ret_1d is not None else None,
            "return_30d": float(ret_30d) if ret_30d is not None else None,
            "return_1y": float(ret_1y) if ret_1y is not None else None,
            "benchmark": "SPY",
            "benchmark_return_1d": float(bench_ret_1d) if bench_ret_1d is not None else None,
            "benchmark_return_30d": float(bench_ret_30d) if bench_ret_30d is not None else None,
            "benchmark_return_1y": float(bench_ret_1y) if bench_ret_1y is not None else None,
            "beta": float(beta) if beta is not None else None,
            "alpha": float(alpha) if alpha is not None else None,
            "info_ratio": float(info_ratio) if info_ratio is not None else None,
            "treynor": float(treynor) if treynor is not None else None,
            "transaction_cost_bps": self.transaction_cost_bps,
            "equity_curve": equity_curve,
            "returns_series": returns_series,
            "drawdown_series": pd.Series(drawdown, index=pd.DatetimeIndex(equity_dates)),
            "rebalance_events": [
                {"date": ev.date.strftime("%Y-%m-%d"), "n_positions": len(ev.weights)}
                for ev in events
            ],
        }


def _progress_enabled() -> bool:
    """
    Whether to show progress bars.

    Default is ON; disable with PROGRESS=0 or NO_PROGRESS=1.
    """
    if os.getenv("NO_PROGRESS", "").strip().lower() in {"1", "true", "yes"}:
        return False
    v = os.getenv("PROGRESS", "").strip().lower()
    if v in {"0", "false", "no"}:
        return False
    return True


class _ProgressBar:
    """
    Minimal progress bar (no extra deps).

    Designed to work with BacktestEngine.fetch_historical_data(progress_callback=...).
    """

    def __init__(self, total: int, prefix: str = "", width: int = 30) -> None:
        self.total = max(1, int(total))
        self.prefix = str(prefix).strip()
        self.width = max(10, int(width))
        self._enabled = _progress_enabled()
        self._start_ts = time.time()
        self._last_draw_ts = 0.0
        self._i = 0

    def callback(self):
        # progress_callback signature: (fraction_0_to_1, message)
        def _cb(frac: float, msg: str = "") -> None:
            if not self._enabled:
                return
            try:
                frac_f = float(frac)
            except Exception:
                frac_f = 0.0
            frac_f = 0.0 if frac_f < 0 else (1.0 if frac_f > 1.0 else frac_f)
            # Map 0..1 to 0..total for a consistent bar.
            i = int(round(frac_f * self.total))
            self._draw(i=i, extra=str(msg or ""))
            if frac_f >= 1.0:
                self._finish()

        return _cb

    def step(self, extra: str = "") -> None:
        if not self._enabled:
            return
        self._i = min(self.total, self._i + 1)
        self._draw(i=self._i, extra=extra)
        if self._i >= self.total:
            self._finish()

    def _draw(self, i: int, extra: str = "") -> None:
        if not self._enabled:
            return
        now = time.time()
        # Throttle redraws to avoid spamming output.
        if (now - self._last_draw_ts) < 0.15 and i < self.total:
            return
        self._last_draw_ts = now

        i = max(0, min(self.total, int(i)))
        frac = i / self.total
        filled = int(round(frac * self.width))
        bar = "#" * filled + "-" * (self.width - filled)

        elapsed = now - self._start_ts
        eta_s = None
        if frac > 0:
            eta = elapsed * (1.0 / frac - 1.0)
            eta_s = int(max(0.0, eta))

        left = f"{self.prefix} " if self.prefix else ""
        eta_txt = f" ETA {eta_s}s" if eta_s is not None and i < self.total else ""
        extra_txt = f" | {extra}" if extra else ""
        line = f"\r{left}[{bar}] {frac*100:6.2f}%{eta_txt}{extra_txt}"

        # Keep it reasonably short for log files.
        if len(line) > 180:
            line = line[:177] + "..."

        sys.stdout.write(line)
        sys.stdout.flush()

    def _finish(self) -> None:
        if not self._enabled:
            return
        # Ensure the cursor moves to the next line.
        sys.stdout.write("\n")
        sys.stdout.flush()
