"""Check plot data format."""
import json
from pathlib import Path

plot_path = Path(".cache/plot_data.json")
val_path = Path(".cache/last_validation_results.json")

print("=" * 80)
print("PLOT DATA (IB Real Data from 2020-01-01)")
print("=" * 80)

plot_data = json.loads(plot_path.read_text(encoding="utf-8"))
for name, strat in sorted(plot_data.get("strategies", {}).items()):
    cagr = strat.get("cagr", 0)
    sharpe = strat.get("sharpe", 0)
    points = len(strat.get("equity_curve", []))
    # CAGR might be stored as decimal (0.30) or percentage (30)
    if cagr > 10:  # Likely stored as percentage * 100
        cagr_display = cagr / 100
    else:
        cagr_display = cagr
    print(f"{name:<45} CAGR: {cagr_display:>7.2%}  Sharpe: {sharpe:>5.2f}  Points: {points}")

print("\n" + "=" * 80)
print("VALIDATION RESULTS (Earlier Backtests)")
print("=" * 80)

val_data = json.loads(val_path.read_text(encoding="utf-8"))
for name, strat in sorted(val_data.get("strategies", {}).items()):
    cagr = strat.get("cagr", 0)
    sharpe = strat.get("sharpe", 0)
    # Validation results store CAGR as percentage (30.59 = 30.59%)
    print(f"{name:<45} CAGR: {cagr:>7.2f}%  Sharpe: {sharpe:>5.2f}")
