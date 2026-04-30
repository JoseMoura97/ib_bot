"""Compare Michael Burry CAGR across all sources."""
import json

print("=" * 70)
print("MICHAEL BURRY CAGR COMPARISON")
print("=" * 70)

# 1. Current plot_data.json (with options filtered out)
with open('.cache/plot_data.json', 'r') as f:
    current = json.load(f)
current_burry = current.get('strategies', {}).get('Michael Burry', {})
print(f"\n1. CURRENT (options filtered out, from 2016):")
print(f"   CAGR: {current_burry.get('cagr', 'N/A'):.2f}%")
print(f"   Sharpe: {current_burry.get('sharpe', 'N/A'):.2f}")
print(f"   Max DD: {current_burry.get('max_drawdown', 'N/A'):.2f}%")
print(f"   Start: {current_burry.get('start_date', 'N/A')}")
print(f"   Points: {len(current_burry.get('values', []))}")

# 2. Legacy backup (with options INCLUDED, from 2020)
try:
    with open('.cache/backups/plot_data_23strategies_FINAL.json', 'r') as f:
        legacy = json.load(f)
    legacy_burry = legacy.get('strategies', {}).get('Michael Burry', {})
    print(f"\n2. LEGACY (options INCLUDED, from 2020):")
    print(f"   CAGR: {legacy_burry.get('cagr', 'N/A'):.2f}%")
    print(f"   Sharpe: {legacy_burry.get('sharpe', 'N/A'):.2f}")
    print(f"   Max DD: {legacy_burry.get('max_drawdown', 'N/A'):.2f}%")
    print(f"   Start: {legacy_burry.get('dates', ['N/A'])[0] if legacy_burry.get('dates') else 'N/A'}")
    print(f"   Points: {len(legacy_burry.get('values', []))}")
except FileNotFoundError:
    print("\n2. LEGACY: File not found")

# 3. Quiver reference
with open('.cache/quiver_strategies_site.json', 'r') as f:
    quiver = json.load(f)
quiver_burry = quiver.get('strategies', {}).get('Michael Burry', {})
print(f"\n3. QUIVER REFERENCE (official):")
print(f"   CAGR: {quiver_burry.get('cagr', 'N/A')}")
print(f"   Sharpe: {quiver_burry.get('sharpe_ratio', 'N/A')}")
print(f"   Max DD: {quiver_burry.get('max_drawdown', 'N/A')}")
print(f"   Start: {quiver_burry.get('start_date', 'N/A')}")
print(f"   Trades: {quiver_burry.get('trades', 'N/A')}")

# 4. quiver_signals.py metadata
print(f"\n4. QUIVER_SIGNALS.PY (metadata):")
try:
    from quiver_signals import QuiverSignals
    signals_meta = getattr(QuiverSignals, 'STRATEGIES_META', {}).get('Michael Burry', {})
    if not signals_meta:
        # Try alternate attribute
        signals_meta = getattr(QuiverSignals, 'HEDGE_FUND_STRATEGIES', {}).get('Michael Burry', {})
    print(f"   CAGR: {signals_meta.get('cagr', 'N/A')}")
    print(f"   Sharpe: {signals_meta.get('sharpe_ratio', 'N/A')}")
    print(f"   Start: {signals_meta.get('start_date', 'N/A')}")
except Exception as e:
    print(f"   Error: {e}")

# Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"{'Source':<35} {'CAGR':<15} {'Period':<20}")
print("-" * 70)
print(f"{'Current (stock only)':<35} {'20.76%':<15} {'2016-present':<20}")
print(f"{'Legacy (incl options)':<35} {'72.77%':<15} {'2020-present':<20}")
print(f"{'Quiver Official':<35} {'30.45%':<15} {'2016-present':<20}")

print("\n" + "=" * 70)
print("WHY THE DIFFERENCES?")
print("=" * 70)
print("""
1. LEGACY (72.77%) vs QUIVER (30.45%):
   - Legacy included OPTIONS (PUT/CALL) as stock positions
   - NVDA Put treated as owning NVDA stock = wrong direction
   - Legacy started from 2020 (best period) vs Quiver from 2016
   
2. CURRENT (20.76%) vs QUIVER (30.45%):
   - Both use stock-only positions
   - Both use same start date (2016)
   - ~10% difference likely due to:
     a) Different price sources (Yahoo vs Bloomberg)
     b) Missing quarters (Burry was in cash/options some periods)
     c) Portfolio weight calculation differences
     
3. QUIVER'S METHODOLOGY:
   - "Mirrors portfolio using 13F filings"
   - "Rebalanced when new filings are reported"
   - Likely uses VALUE-WEIGHTED positions (not equal-weighted)
   - May include some option exposure that we filter out
""")
