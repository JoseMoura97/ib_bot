"""
Generate equity curve plot data for strategies vs SPY benchmark.
Saves JSON data that can be embedded in HTML for interactive charts.
"""

import json
import os
import sys
from datetime import datetime
import pandas as pd
import numpy as np

from dotenv import load_dotenv
from quiver_signals import QuiverSignals
from rebalancing_backtest_engine import RebalancingBacktestEngine, _ProgressBar
from run_all_backtests import STRATEGY_REGISTRY

def normalize_equity_curve(equity_curve_df, initial_value=100):
    """Normalize an equity curve to start at initial_value (e.g., 100)."""
    if equity_curve_df is None or equity_curve_df.empty:
        return pd.DataFrame()
    
    # Handle both 'equity' and 'portfolio_value' column names
    if 'equity' in equity_curve_df.columns:
        value_col = 'equity'
    elif 'portfolio_value' in equity_curve_df.columns:
        value_col = 'portfolio_value'
    else:
        return pd.DataFrame()
    
    first_value = equity_curve_df[value_col].iloc[0]
    if first_value <= 0:
        first_value = 1.0
    
    equity_curve_df = equity_curve_df.copy()
    equity_curve_df['normalized'] = (equity_curve_df[value_col] / first_value) * initial_value
    return equity_curve_df

def generate_plot_data(use_cache_only: bool = False):
    """Generate plot data for all strategies vs SPY.
    
    Args:
        use_cache_only: If True, use only cached price data (no API calls).
                        This runs real backtests on cached historical prices.
    """
    print("Generating plot data for all strategies vs SPY...")
    print("="*80)
    
    load_dotenv()
    api_key = os.getenv("QUIVER_API_KEY")
    if not api_key:
        raise SystemExit("QUIVER_API_KEY is required")
    
    # Determine price source
    if use_cache_only:
        price_source = "cache_only"
        print("Using CACHE_ONLY mode - no external API calls")
    else:
        price_source = os.getenv("PRICE_SOURCE", "auto")
        print(f"Using price source: {price_source}")
    
    qs = QuiverSignals(api_key)
    bt = RebalancingBacktestEngine(
        quiver_api_key=api_key,
        initial_capital=100000,
        transaction_cost_bps=0.0,
        price_source=price_source,
    )
    
    # Output structure
    plot_data = {
        "generated_at": datetime.now().isoformat(),
        "data_source": "cached_prices" if use_cache_only else "live_api",
        "synthetic": False,  # These are REAL backtests, not synthetic curves
        "strategies": {},
        "benchmark": None
    }
    
    # Use the canonical registry so dashboard plot data stays aligned with
    # run_all_backtests.py, including generated alpha-only variants.
    strategies = [
        (s.name, s.base_name or s.name, s.alpha_only)
        for s in STRATEGY_REGISTRY
        if s.enabled
    ]
    
    # Get SPY benchmark data — fetch directly via yfinance (not via backtest engine)
    overall = _ProgressBar(total=len(strategies) + 1, prefix="Plot data", width=30)

    print("\nFetching SPY benchmark...")
    try:
        import yfinance as yf
        benchmark_start = "2008-01-01"
        spy = yf.download("SPY", start=benchmark_start, progress=False)
        if spy is not None and not spy.empty:
            close_col = 'Close'
            if isinstance(spy.columns, pd.MultiIndex):
                spy.columns = spy.columns.get_level_values(0)
            spy_prices = spy[[close_col]].copy()
            spy_prices.columns = ['price']
            first_price = spy_prices['price'].iloc[0]
            spy_prices['normalized'] = (spy_prices['price'] / first_price) * 100
            spy_weekly = spy_prices.resample('W-FRI').last().ffill()
            spy_weekly = spy_weekly.dropna()
            plot_data['benchmark'] = {
                "name": "SPY",
                "dates": spy_weekly.index.strftime('%Y-%m-%d').tolist(),
                "values": spy_weekly['normalized'].round(2).tolist()
            }
            print(f"[OK] SPY: {len(spy_weekly)} weekly points from {spy_weekly.index[0].date()} to {spy_weekly.index[-1].date()}")
        else:
            print("[WARN] SPY: no data returned from yfinance")
        overall.step(extra="SPY")
    except Exception as e:
        print(f"[ERROR] SPY Error: {e}")
        import traceback
        traceback.print_exc()
        overall.step(extra="SPY error")
    
    # Generate data for each strategy — use each strategy's actual start date
    # for accurate CAGR (previously clipped to 2020-01-01 which understated returns)
    
    strategy_count = 0
    for strategy_name, base_strategy_name, alpha_only in strategies:
        try:
            print(f"\n{strategy_name}...")

            # Look up strategy info; if the variant name has decoration like
            # "(equal)", "(size)", or "(alpha only)" the canonical key is the
            # un-suffixed base, so progressively strip suffixes until we hit a
            # known entry.
            info = qs.get_strategy_info(base_strategy_name)
            if not info or not info.get("start_date"):
                stripped = base_strategy_name
                for suffix in [" (alpha only)", " (equal)", " (size)"]:
                    if stripped.endswith(suffix):
                        stripped = stripped[: -len(suffix)]
                        cand = qs.get_strategy_info(stripped)
                        if cand and cand.get("start_date"):
                            info = cand
                            break
            if not info or not info.get("start_date"):
                # Final fallback: use 2014-01-01 (covers all Quiver-data strategies).
                info = {"start_date": "2014-01-01"}

            start_date_str = info['start_date']
            start_date = datetime.fromisoformat(start_date_str)
            
            # Run backtest using run_rebalancing_backtest
            result = bt.run_rebalancing_backtest(
                strategy_name=base_strategy_name,
                start_date=start_date,
                end_date=datetime.now(),
                lookback_days_override=None,
                alpha_only=alpha_only,
            )
            
            if result and 'equity_curve' in result and not 'error' in result:
                equity_curve = normalize_equity_curve(result['equity_curve'], 100)
                
                if not equity_curve.empty:
                    # Downsample to weekly data to reduce file size
                    equity_curve_weekly = equity_curve.resample('W-FRI').last().ffill()
                    
                    cagr = result.get('cagr', 0)
                    sharpe = result.get('sharpe_ratio', 0)
                    max_dd = result.get('max_drawdown', 0)
                    sortino = result.get('sortino_ratio', 0)
                    
                    # Convert to percentages
                    cagr_pct = cagr * 100 if isinstance(cagr, (int, float)) else 0
                    max_dd_pct = max_dd * 100 if isinstance(max_dd, (int, float)) else 0
                    
                    plot_data['strategies'][strategy_name] = {
                        "name": strategy_name,
                        "dates": equity_curve_weekly.index.strftime('%Y-%m-%d').tolist(),
                        "values": equity_curve_weekly['normalized'].round(2).tolist(),
                        "start_date": start_date_str,
                        "alpha_only": bool(alpha_only),
                        "cagr": float(cagr_pct),
                        "sharpe": float(sharpe) if isinstance(sharpe, (int, float)) else 0,
                        "sortino": float(sortino) if isinstance(sortino, (int, float)) else 0,
                        "max_drawdown": float(max_dd_pct),
                        "transaction_cost_bps": result.get('transaction_cost_bps'),
                        "slippage_bps_per_side": result.get('slippage_bps_per_side'),
                        "execution_offset_days": result.get('execution_offset_days'),
                        "missing_ticker_policy": result.get('missing_ticker_policy'),
                        "n_missing_ticker_segments": result.get('n_missing_ticker_segments'),
                    }
                    
                    strategy_count += 1
                    print(f"  [OK] {len(equity_curve_weekly)} weekly points, CAGR={cagr_pct:.1f}%")
                    overall.step(extra=f"ok: {strategy_name}")
                else:
                    print(f"  [SKIP] Empty equity curve")
                    overall.step(extra=f"skip: {strategy_name}")
            elif 'error' in result:
                print(f"  [ERROR] Backtest error: {result['error']}")
                overall.step(extra=f"error: {strategy_name}")
            else:
                print(f"  [SKIP] No backtest result")
                overall.step(extra=f"skip: {strategy_name}")
                
        except Exception as e:
            print(f"  [ERROR] Error: {e}")
            import traceback
            traceback.print_exc()
            overall.step(extra=f"error: {strategy_name}")
            continue
    
    print(f"\n{'='*80}")
    print(f"Generated plot data for {strategy_count}/{len(strategies)} strategies")
    
    output_file = os.environ.get("PLOT_DATA_OUTPUT_PATH") or '.cache/plot_data.json'
    os.makedirs(os.path.dirname(output_file) or '.', exist_ok=True)
    plot_data["missing_ticker_policy"] = os.environ.get("MISSING_TICKER_POLICY", "cash")

    if strategy_count == 0:
        print("[SKIP] Not writing plot_data.json — 0 strategies succeeded")
        return plot_data
    
    with open(output_file, 'w') as f:
        json.dump(plot_data, f, indent=2)
    
    file_size = os.path.getsize(output_file) / 1024
    print(f"[OK] Saved to {output_file} ({file_size:.1f} KB)")
    
    return plot_data

if __name__ == "__main__":
    import warnings
    import argparse
    warnings.filterwarnings('ignore')
    
    parser = argparse.ArgumentParser(description="Generate plot data for strategies")
    parser.add_argument("--cache-only", action="store_true",
                        help="Use only cached price data (no external API calls)")
    parser.add_argument("--cache-dir", type=str, default=".cache",
                        help="Cache directory path")
    parser.add_argument("--no-progress", action="store_true",
                        help="Disable progress bars")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Pre-confirm api_caution gate")
    parser.add_argument("--budget-estimate", action="store_true",
                        help="Print estimated API call volume and exit")
    parser.add_argument("--policy", choices=["cash", "renormalize"], default="cash",
                        help="Missing-ticker policy applied during backtest")
    parser.add_argument("--output", type=str, default=None,
                        help="Override plot_data output path (default: .cache/plot_data.json)")
    args = parser.parse_args()

    # Apply policy via env so the engine picks it up.
    os.environ["MISSING_TICKER_POLICY"] = args.policy
    if args.output:
        os.environ["PLOT_DATA_OUTPUT_PATH"] = args.output

    # Set environment variables for backtesting
    os.environ['PYTHONUNBUFFERED'] = '1'
    if not args.cache_only:
        os.environ['PRICE_SOURCE'] = os.getenv('PRICE_SOURCE', 'auto')

    # ── API-caution gate ──────────────────────────────────────────────────
    if not args.cache_only:
        try:
            from api_caution import estimate_calls, confirm_or_abort, CautionAbort
            # generate_plot_data runs all strategies — conservative estimate.
            est = estimate_calls(
                n_tickers=150 * 30,  # ~30 strategies * 150 tickers
                n_strategies=30,
                source=os.environ.get('PRICE_SOURCE', 'auto'),
            )
            if args.budget_estimate:
                print(f"api_caution budget estimate: {est} calls (source={os.environ.get('PRICE_SOURCE')})")
                sys.exit(0)
            try:
                confirm_or_abort(
                    estimated_calls=est,
                    source=os.environ.get('PRICE_SOURCE', 'auto'),
                    yes=args.yes,
                    reason="generate_plot_data.py",
                )
            except CautionAbort as ce:
                print(f"api_caution: refusing run. {ce}")
                sys.exit(2)
        except ImportError:
            pass
    if args.no_progress:
        os.environ['NO_PROGRESS'] = '1'
    else:
        # Default progress to ON unless user has explicitly disabled it.
        if os.getenv("NO_PROGRESS", "").strip().lower() not in {"1", "true", "yes"}:
            if os.getenv("PROGRESS", "").strip() == "":
                os.environ["PROGRESS"] = "1"
    
    try:
        plot_data = generate_plot_data(use_cache_only=args.cache_only)
        
        if plot_data and plot_data.get('strategies'):
            print("\n[OK] Plot data generation complete!")
            print(f"  Strategies: {len(plot_data['strategies'])}")
            print(f"  Data source: {plot_data.get('data_source', 'unknown')}")
            print(f"  Synthetic: {plot_data.get('synthetic', False)}")
            if plot_data.get('benchmark'):
                print(f"  Benchmark: SPY with {len(plot_data['benchmark']['dates'])} points")
        else:
            print("\n[ERROR] No plot data generated")
            sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
