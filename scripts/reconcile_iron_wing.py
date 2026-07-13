#!/usr/bin/env python3
"""Offline Iron Wing reconciliation across real Theta intraday and EOD regimes."""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


def finite(values) -> np.ndarray:
    array = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)
    return array[np.isfinite(array)]


def scenario_stats(values, dates, seed: int = 713) -> tuple[dict, pd.DataFrame]:
    frame = pd.DataFrame({"ret": pd.to_numeric(values, errors="coerce"), "date": pd.to_datetime(dates)})
    frame = frame[np.isfinite(frame["ret"])].sort_values("date").reset_index(drop=True)
    a = frame["ret"].to_numpy(float)
    if not len(a):
        return {"n": 0}, pd.DataFrame(columns=["date", "equity"])
    gains, losses = a[a > 0].sum(), -a[a < 0].sum()
    pf = gains / losses if losses else None
    equity = np.cumprod(1.0 + 0.01 * np.clip(a, -1.0, None))
    drawdown = equity / np.maximum.accumulate(equity) - 1.0
    span_days = max((frame["date"].max() - frame["date"].min()).days, 1)
    years = span_days / 365.25
    cagr = equity[-1] ** (1 / years) - 1 if years > 0 else None
    events_per_year = len(a) / years
    sharpe = (a.mean() / a.std(ddof=1) * math.sqrt(events_per_year)) if len(a) > 1 and a.std(ddof=1) else None
    rng = np.random.default_rng(seed)
    bootstrap = rng.choice(a, size=(2000, len(a)), replace=True).mean(axis=1)
    stats = {
        "n": len(a),
        "mean_return": float(a.mean()),
        "median_return": float(np.median(a)),
        "win_rate": float((a > 0).mean()),
        "profit_factor": float(pf) if pf is not None else None,
        "mean_return_bootstrap_95_ci": [float(np.quantile(bootstrap, 0.025)), float(np.quantile(bootstrap, 0.975))],
        "normalized_1pct_risk_total_return": float(equity[-1] - 1),
        "normalized_1pct_risk_max_drawdown": float(drawdown.min()),
        "normalized_1pct_risk_cagr": float(cagr) if cagr is not None else None,
        "event_sharpe": float(sharpe) if sharpe is not None else None,
        "start": frame["date"].min().date().isoformat(),
        "end": frame["date"].max().date().isoformat(),
    }
    curve = pd.DataFrame({"date": frame["date"], "equity": equity})
    return stats, curve


def by_year(values, dates) -> dict:
    frame = pd.DataFrame({"ret": pd.to_numeric(values, errors="coerce"), "date": pd.to_datetime(dates)})
    frame = frame[np.isfinite(frame.ret)]
    result = {}
    for year, group in frame.groupby(frame.date.dt.year):
        a = group.ret.to_numpy(float)
        loss = -a[a < 0].sum()
        result[str(year)] = {
            "n": len(a), "mean_return": float(a.mean()), "win_rate": float((a > 0).mean()),
            "profit_factor": float(a[a > 0].sum() / loss) if loss else None,
        }
    return result


def ironfly_with_commission(ec, xc, atm: float, wing: float, slip: float,
                            roundtrip_commission: float = 0.052) -> float | None:
    """Reprice the stored four-leg fly including $5.20 round-trip commission.

    Option quotes are dollars per share, so eight $0.65 contract charges are
    0.052 quote units.  This intentionally mirrors the historical engine's
    max-risk denominator and -100% floor.
    """
    common = [strike for strike in ec if strike in xc]
    if atm not in common:
        return None
    low = min(common, key=lambda strike: abs(strike - atm * (1 - wing)))
    high = min(common, key=lambda strike: abs(strike - atm * (1 + wing)))
    if not low < atm < high:
        return None
    entry_atm, exit_atm = ec[atm], xc[atm]
    entry_low, entry_high, exit_low, exit_high = ec[low], ec[high], xc[low], xc[high]

    def valid(quote, *keys):
        return quote is not None and all(
            key in quote and np.isfinite(quote[key]) and quote[key] > 0 for key in keys
        )

    if not (
        valid(entry_atm, "c_bid", "c_ask", "p_bid", "p_ask")
        and valid(exit_atm, "c_bid", "c_ask", "p_bid", "p_ask")
        and valid(entry_low, "p_bid", "p_ask")
        and valid(entry_high, "c_bid", "c_ask")
        and valid(exit_low, "p_bid", "p_ask")
        and valid(exit_high, "c_bid", "c_ask")
    ):
        return None

    sell = lambda bid, ask: (bid + ask) / 2 - slip * (ask - bid)
    buy = lambda bid, ask: (bid + ask) / 2 + slip * (ask - bid)
    entry = (
        sell(entry_atm["c_bid"], entry_atm["c_ask"])
        + sell(entry_atm["p_bid"], entry_atm["p_ask"])
        - buy(entry_low["p_bid"], entry_low["p_ask"])
        - buy(entry_high["c_bid"], entry_high["c_ask"])
    )
    exit_debit = (
        buy(exit_atm["c_bid"], exit_atm["c_ask"])
        + buy(exit_atm["p_bid"], exit_atm["p_ask"])
        - sell(exit_low["p_bid"], exit_low["p_ask"])
        - sell(exit_high["c_bid"], exit_high["c_ask"])
    )
    width = min(atm - low, high - atm)
    max_risk = width - entry + roundtrip_commission
    if width <= 0 or max_risk < 0.10 * width:
        return None
    return float(max(((entry - exit_debit) - roundtrip_commission) / max_risk, -1.0))


def compact_stats(values) -> dict:
    array = finite(values)
    if not len(array):
        return {"n": 0, "mean_return_pct": None, "profit_factor": None, "win_rate": None}
    losses = -array[array < 0].sum()
    return {
        "n": int(len(array)),
        "mean_return_pct": float(array.mean() * 100),
        "profit_factor": float(array[array > 0].sum() / losses) if losses else None,
        "win_rate": float((array > 0).mean()),
    }


def historical_timing_audit(intraday: pd.DataFrame, source: pd.DataFrame, bulk: Path) -> dict:
    """Reproduce and pin the 2026-07-13 BMO/AMC timing audit from disk."""
    cutoff = pd.Timestamp("2022-12-31")
    held_source = source[source.earnings_date > cutoff]
    held = intraday[intraday.earnings_date > cutoff]
    amc = held[held.when == "AMC"]
    bmo = held[held.when == "BMO"]

    correct_bmo_entry_files = 0
    held_bmo_source = held_source[held_source.when == "BMO"]
    for _, row in held_bmo_source.iterrows():
        prior_session = pd.Timestamp(row.earnings_date) - pd.offsets.BDay(1)
        candidate = bulk / str(row.symbol) / f"{row.front_exp}_{prior_session.date()}.parquet"
        correct_bmo_entry_files += int(candidate.exists())

    recomputed = {
        "valid_amc_heldout": {
            "slip_0.10": compact_stats(amc["ret_slip_0.10"]),
            "slip_0.25": compact_stats(amc["ret_slip_0.25"]),
            "slip_0.10_commission_5_20": compact_stats(amc["ret_commission_slip_0.10"]),
            "slip_0.25_commission_5_20": compact_stats(amc["ret_commission_slip_0.25"]),
        },
        "invalid_bmo_shifted_window": {
            "slip_0.10": compact_stats(bmo["ret_slip_0.10"]),
            "slip_0.25": compact_stats(bmo["ret_slip_0.25"]),
        },
    }
    expected = {
        "valid_amc_heldout": {
            "slip_0.10": {"n": 530, "mean_return_pct": 18.53, "profit_factor": 1.986},
            "slip_0.25": {"n": 531, "mean_return_pct": 13.27, "profit_factor": 1.643},
            "slip_0.10_commission_5_20": {"n": 531, "mean_return_pct": 15.40, "profit_factor": 1.801},
            "slip_0.25_commission_5_20": {"n": 531, "mean_return_pct": 10.01, "profit_factor": 1.475},
        },
        "invalid_bmo_shifted_window": {
            "slip_0.10": {"n": 347, "mean_return_pct": -1.02, "profit_factor": 0.837},
            "slip_0.25": {"n": 347, "mean_return_pct": -3.69, "profit_factor": 0.520},
        },
    }
    checks = []
    for group, scenarios in expected.items():
        for scenario, target in scenarios.items():
            actual = recomputed[group][scenario]
            checks.extend((
                actual["n"] == target["n"],
                round(actual["mean_return_pct"], 2) == target["mean_return_pct"],
                round(actual["profit_factor"], 3) == target["profit_factor"],
            ))
    checks.extend((
        len(source) == 3264,
        int((source.when == "BMO").sum()) == 1750,
        int((source.when == "AMC").sum()) == 1514,
        len(held_bmo_source) == 1296,
        correct_bmo_entry_files == 0,
    ))
    return {
        "evidence_version": "iron-wing-timing-audit-v1-2026-07-13",
        "provenance": {
            "source_dataset": "intraday_events.parquet plus its referenced on-disk Theta bulk chains",
            "method": "reprice 10%-wing hold-to-close flies from stored chains; split heldout 2023+ by original when field",
            "roundtrip_commission_usd": 5.20,
            "live_or_paid_api_calls": 0,
        },
        "source_counts": {
            "all": len(source),
            "bmo": int((source.when == "BMO").sum()),
            "amc": int((source.when == "AMC").sum()),
            "heldout_bmo": len(held_bmo_source),
        },
        "bug": {
            "description": "The historical builder normalized raw timing to 'BMO', then passed that token through _classify_when again. The classifier recognized only strings containing 'before', so literal 'BMO' fell through to AMC and _reaction_date shifted the window one day late.",
            "effect": "The invalid BMO rows lose money and therefore drag the combined headline; they do not create the AMC alpha.",
        },
        "correct_prior_day_theta_raw_availability": {
            "available": correct_bmo_entry_files,
            "required": len(held_bmo_source),
            "coverage_pct": correct_bmo_entry_files / len(held_bmo_source) if len(held_bmo_source) else None,
        },
        "expected_rounded_audit_values": expected,
        "recomputed_from_disk": recomputed,
        "all_expected_values_verified": all(checks),
    }


def eod_reprice(row: pd.Series, trading: Path, slip: float) -> tuple[float, dict] | tuple[None, dict]:
    earnings = pd.Timestamp(row.earnings_date)
    when = str(row.get("when", "")).lower()
    reaction = earnings if "before" in when else earnings + pd.Timedelta(days=1)
    candidates = [
        trading / "data" / "options" / row.symbol / "events3" / f"{reaction.date()}.parquet",
        trading / "data" / "options" / row.symbol / "events3" / f"{earnings.date()}.parquet",
    ]
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if path is None:
        return None, {"reason": "raw_event_file_missing"}
    window = pd.read_parquet(path)
    window["date"] = pd.to_datetime(window["date"])
    window["expiration"] = pd.to_datetime(window["expiration"])
    entry, exit_ = pd.Timestamp(row.entry_date), pd.Timestamp(row.exit_date)
    expiry, atm = pd.Timestamp(row.front_exp), float(row.strike)
    entry_slice, exit_slice = window[window.date == entry], window[window.date == exit_]
    strikes = sorted(set(entry_slice.loc[entry_slice.expiration == expiry, "strike"])
                     & set(exit_slice.loc[exit_slice.expiration == expiry, "strike"]))
    if not strikes:
        return None, {"reason": "no_common_strikes"}
    low = min(strikes, key=lambda strike: abs(strike - atm * 0.90))
    high = min(strikes, key=lambda strike: abs(strike - atm * 1.10))
    if not low < atm < high:
        return None, {"reason": "invalid_wings"}

    def quote(frame, strike, call_put):
        matched = frame[(frame.expiration == expiry) & np.isclose(frame.strike, strike)
                        & (frame.call_put == call_put)]
        if matched.empty:
            return None
        record = matched.iloc[0]
        bid, ask = float(record.bid), float(record.ask)
        return (bid, ask) if np.isfinite(bid) and np.isfinite(ask) and ask > 0 else None

    entry_quotes = [quote(entry_slice, atm, "Call"), quote(entry_slice, atm, "Put"),
                    quote(entry_slice, low, "Put"), quote(entry_slice, high, "Call")]
    exit_quotes = [quote(exit_slice, atm, "Call"), quote(exit_slice, atm, "Put"),
                   quote(exit_slice, low, "Put"), quote(exit_slice, high, "Call")]
    if any(value is None for value in entry_quotes + exit_quotes):
        return None, {"reason": "incomplete_quotes"}

    def sell(q):
        return (q[0] + q[1]) / 2 - slip * (q[1] - q[0])

    def buy(q):
        return (q[0] + q[1]) / 2 + slip * (q[1] - q[0])

    entry_value = sell(entry_quotes[0]) + sell(entry_quotes[1]) - buy(entry_quotes[2]) - buy(entry_quotes[3])
    exit_value = buy(exit_quotes[0]) + buy(exit_quotes[1]) - sell(exit_quotes[2]) - sell(exit_quotes[3])
    width = min(atm - low, high - atm)
    commission = 8 * 0.65 / 100
    max_risk = width - entry_value + commission
    if width <= 0 or max_risk < 0.10 * width:
        return None, {"reason": "invalid_max_risk"}
    result = max(((entry_value - exit_value) - commission) / max_risk, -1.0)
    total_spread = sum(ask - bid for bid, ask in entry_quotes)
    return float(result), {
        "quoted_spread_to_entry_credit": float(total_spread / entry_value) if entry_value > 0 else None,
        "wing_width": width,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trading-root", type=Path, default=Path("/home/servidor/Desktop/cursor-projects/trading"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    trading, out = args.trading_root.resolve(), args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(trading))
    from studies.exploration.ironfly_params import BULK, EVENTS, EXIT_MS, PRE_CLOSE, _load, chain_at, ironfly

    intraday_events = pd.read_parquet(EVENTS)
    intraday_events["earnings_date"] = pd.to_datetime(intraday_events.earnings_date)
    intraday_rows = []
    for _, row in intraday_events.iterrows():
        entry_raw = _load(BULK / row.symbol / f"{row.front_exp}_{row.entry_date}.parquet")
        exit_raw = _load(BULK / row.symbol / f"{row.front_exp}_{row.exit_date}.parquet")
        if entry_raw is None or exit_raw is None:
            continue
        entry_chain = chain_at(entry_raw, PRE_CLOSE)
        exit_chain = chain_at(exit_raw, EXIT_MS["1545"])
        record = {
            "symbol": row.symbol, "earnings_date": row.earnings_date,
            "when": str(row.when).upper(),
            "entry_date": pd.Timestamp(row.entry_date), "exit_date": pd.Timestamp(row.exit_date),
            "front_exp": pd.Timestamp(row.front_exp), "strike": float(row.atm),
        }
        for slip in (0.0, 0.10, 0.25):
            record[f"ret_slip_{slip:.2f}"] = ironfly(entry_chain, exit_chain, float(row.atm), 0.10, slip)
        for slip in (0.10, 0.25):
            record[f"ret_commission_slip_{slip:.2f}"] = ironfly_with_commission(
                entry_chain, exit_chain, float(row.atm), 0.10, slip
            )
        intraday_rows.append(record)
    intraday = pd.DataFrame(intraday_rows)
    intraday.to_parquet(out / "intraday_repriced_events.parquet", index=False)

    eod = pd.read_parquet(trading / "backtests/reports/0006_earnings_vol/events_multiregime.parquet")
    eod["earnings_date"] = pd.to_datetime(eod.earnings_date)
    eod_mid, eod_q25, quote_ratios, reasons = [], [], [], {}
    for _, row in eod.iterrows():
        mid, diag_mid = eod_reprice(row, trading, 0.0)
        quoted, diag_quoted = eod_reprice(row, trading, 0.25)
        eod_mid.append(mid); eod_q25.append(quoted)
        ratio = diag_quoted.get("quoted_spread_to_entry_credit")
        if ratio is not None and np.isfinite(ratio):
            quote_ratios.append(ratio)
        if mid is None:
            reason = diag_mid.get("reason", "unknown")
            reasons[reason] = reasons.get(reason, 0) + 1
    eod["ironfly_ret_mid_repriced"] = eod_mid
    eod["ironfly_ret_slip025_repriced"] = eod_q25
    eod.to_parquet(out / "eod_repriced_events.parquet", index=False)

    scenarios = {
        "intraday_mid_all": (intraday["ret_slip_0.00"], intraday.earnings_date),
        "intraday_slip010_all": (intraday["ret_slip_0.10"], intraday.earnings_date),
        "intraday_slip025_all": (intraday["ret_slip_0.25"], intraday.earnings_date),
        "eod_mid_all": (eod.ironfly_ret_mid_repriced, eod.earnings_date),
        "eod_slip025_all": (eod.ironfly_ret, eod.earnings_date),
    }
    held = intraday.earnings_date > pd.Timestamp("2022-12-31")
    scenarios.update({
        "intraday_mid_heldout_2023plus": (intraday.loc[held, "ret_slip_0.00"], intraday.loc[held, "earnings_date"]),
        "intraday_slip010_heldout_2023plus": (intraday.loc[held, "ret_slip_0.10"], intraday.loc[held, "earnings_date"]),
        "intraday_slip025_heldout_2023plus": (intraday.loc[held, "ret_slip_0.25"], intraday.loc[held, "earnings_date"]),
    })
    metrics, curves = {}, []
    for name, (returns, dates) in scenarios.items():
        stats, curve = scenario_stats(returns, dates)
        stats["by_year"] = by_year(returns, dates)
        metrics[name] = stats
        curve["scenario"] = name
        curves.append(curve)
    pd.concat(curves, ignore_index=True).to_csv(out / "equity_curves.csv", index=False)

    overlap = intraday.merge(
        eod, on=["symbol", "earnings_date"], how="inner", suffixes=("_intraday", "_eod")
    )
    both = overlap[["ret_slip_0.25", "ironfly_ret"]].dropna()
    universe_file = trading / "live/options_cache/universe.txt"
    fixed_universe = {line.strip() for line in universe_file.read_text().splitlines()
                      if line.strip() and not line.startswith("#")}
    legacy_universe_map = {"FI": "FISV", "SQ": "XYZ", "HES": None, "MRO": None,
                           "PARA": None, "WBA": None, "X": None}
    historical_symbols = set(intraday_events.symbol)
    snapshot_files = sorted((trading / "data/options_cache").glob("dt=*/snap_*.parquet"))
    snapshot_symbols: set[str] = set()
    snapshot_days = []
    for path in snapshot_files:
        snapshot_days.append(path.parent.name.split("=", 1)[1])
        try:
            snapshot_symbols.update(pd.read_parquet(path, columns=["symbol"]).symbol.astype(str).unique())
        except Exception:
            pass
    yahoo_calendar_path = trading / "data/options_cache/earnings_calendar_yahoo.parquet"
    yahoo_calendar = pd.read_parquet(yahoo_calendar_path) if yahoo_calendar_path.exists() else pd.DataFrame()
    dolt_max = None
    try:
        process = subprocess.run(
            [str(Path.home() / ".local/bin/dolt"), "sql", "-q", "SELECT MAX(`date`) AS max_date FROM earnings_calendar", "-r", "csv"],
            cwd="/home/servidor/dolt-data/earnings", capture_output=True, text=True, timeout=60,
        )
        if process.returncode == 0 and len(process.stdout.splitlines()) > 1:
            dolt_max = process.stdout.splitlines()[1].strip()
    except Exception:
        pass

    q = np.asarray(quote_ratios, dtype=float)
    stored_vs_repriced = eod[["ironfly_ret", "ironfly_ret_slip025_repriced"]].dropna()
    timing_audit = historical_timing_audit(intraday, intraday_events, Path(BULK))
    payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "intraday_dataset": str(Path(EVENTS)), "intraday_rows": len(intraday_events),
            "intraday_repriced_rows": len(intraday), "intraday_symbols": int(intraday_events.symbol.nunique()),
            "intraday_date_range": [str(intraday_events.earnings_date.min().date()), str(intraday_events.earnings_date.max().date())],
            "theta_bulk_files": len(list(Path(BULK).glob("*/*.parquet"))),
            "eod_dataset": str(trading / "backtests/reports/0006_earnings_vol/events_multiregime.parquet"),
            "eod_rows": len(eod), "eod_symbols": int(eod.symbol.nunique()),
            "eod_date_range": [str(eod.earnings_date.min().date()), str(eod.earnings_date.max().date())],
        },
        "scenarios": metrics,
        "historical_timing_audit": timing_audit,
        "reconciliation": {
            "event_intersection": len(overlap),
            "symbol_intersection": len(set(intraday.symbol) & set(eod.symbol)),
            "same_entry_date_pct": float((overlap.entry_date_intraday == pd.to_datetime(overlap.entry_date_eod)).mean()) if len(overlap) else None,
            "same_exit_date_pct": float((overlap.exit_date_intraday == pd.to_datetime(overlap.exit_date_eod)).mean()) if len(overlap) else None,
            "same_expiration_pct": float((overlap.front_exp_intraday == pd.to_datetime(overlap.front_exp_eod)).mean()) if len(overlap) else None,
            "median_abs_atm_difference": float((overlap.strike_intraday - overlap.strike_eod).abs().median()) if len(overlap) else None,
            "slip025_overlap_return_correlation": float(both.corr().iloc[0, 1]) if len(both) > 1 else None,
            "eod_weekend_entry_pct": float(pd.to_datetime(eod.entry_date).dt.dayofweek.ge(5).mean()),
            "eod_weekend_exit_pct": float(pd.to_datetime(eod.exit_date).dt.dayofweek.ge(5).mean()),
            "intraday_weekend_entry_pct": float(pd.to_datetime(intraday.entry_date).dt.dayofweek.ge(5).mean()),
            "intraday_front_dte_median": float((intraday.front_exp - intraday.entry_date).dt.days.median()),
            "eod_front_dte_median": float(pd.to_numeric(eod.front_dte).median()),
            "eod_quoted_spread_to_credit": {
                "n": len(q), "median": float(np.median(q)) if len(q) else None,
                "p75": float(np.quantile(q, .75)) if len(q) else None,
                "p90": float(np.quantile(q, .90)) if len(q) else None,
            },
            "eod_reprice_unavailable_reasons": reasons,
            "eod_stored_vs_repriced_slip025_mae": float(
                (stored_vs_repriced.ironfly_ret - stored_vs_repriced.ironfly_ret_slip025_repriced).abs().mean()
            ) if len(stored_vs_repriced) else None,
        },
        "forward_coverage": {
            "fixed_universe_symbols": len(fixed_universe),
            "historical_intraday_symbols_currently_listed": len(historical_symbols & fixed_universe),
            "historical_intraday_current_listing_coverage_pct": len(historical_symbols & fixed_universe) / intraday_events.symbol.nunique(),
            "historical_intraday_symbols_accounted_for_including_legacy": len(
                historical_symbols & (fixed_universe | set(legacy_universe_map))
            ),
            "legacy_symbol_map": legacy_universe_map,
            "snapshot_files": len(snapshot_files), "snapshot_symbols_observed": len(snapshot_symbols),
            "snapshot_date_range": [min(snapshot_days), max(snapshot_days)] if snapshot_days else None,
            "dolt_calendar_max_date": dolt_max,
            "yahoo_calendar_rows": len(yahoo_calendar),
            "yahoo_calendar_symbols": int(yahoo_calendar.act_symbol.nunique()) if len(yahoo_calendar) else 0,
            "forward_ledger_exists": (trading / "data/options_cache/paper_ironfly_ledger.parquet").exists(),
        },
        "safety": {"mode": "offline_research", "ib_requests": 0, "orders_placed": 0, "subscriptions_purchased": 0},
    }
    (out / "reconciliation_metrics.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"intraday_repriced": len(intraday), "eod": len(eod), "overlap": len(overlap),
                      "output": str(out / "reconciliation_metrics.json")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
