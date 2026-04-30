"""Compare current plot data with validation results."""
import json
from pathlib import Path

# Load both data sources
plot_path = Path(".cache/plot_data.json")
validation_path = Path(".cache/last_validation_results.json")

print("=" * 80)
print("COMPARISON: Current IB Backtests vs Earlier Validation Results")
print("=" * 80)

# Load plot data (current IB backtests)
if plot_path.exists():
    plot_data = json.loads(plot_path.read_text(encoding="utf-8"))
    print(f"\nCurrent Plot Data:")
    print(f"  Generated: {plot_data.get('generated_at', 'N/A')}")
    print(f"  Data Source: {plot_data.get('data_source', 'N/A')}")
    print(f"  Strategies: {len(plot_data.get('strategies', {}))}")
else:
    plot_data = {"strategies": {}}
    print("\nNo plot_data.json found")

# Load validation results (earlier backtests)
if validation_path.exists():
    validation_data = json.loads(validation_path.read_text(encoding="utf-8"))
    print(f"\nValidation Results:")
    print(f"  Generated: {validation_data.get('generated_at', 'N/A')}")
    print(f"  Strategies: {len(validation_data.get('strategies', {}))}")
else:
    validation_data = {"strategies": {}}
    print("\nNo last_validation_results.json found")

print("\n" + "=" * 80)
print(f"{'Strategy':<40} {'IB CAGR':<12} {'Val CAGR':<12} {'Diff':<12}")
print("=" * 80)

# Combine all strategies
all_strategies = set(plot_data.get("strategies", {}).keys()) | set(validation_data.get("strategies", {}).keys())

for name in sorted(all_strategies):
    # Get current IB data
    ib_strat = plot_data.get("strategies", {}).get(name, {})
    ib_cagr = ib_strat.get("cagr")
    
    # Get validation data
    val_strat = validation_data.get("strategies", {}).get(name, {})
    val_cagr = val_strat.get("our_cagr") or val_strat.get("cagr")
    
    # Format values
    ib_str = f"{ib_cagr:.2%}" if ib_cagr is not None else "---"
    val_str = f"{val_cagr:.2%}" if val_cagr is not None else "---"
    
    # Calculate difference
    if ib_cagr is not None and val_cagr is not None:
        diff = ib_cagr - val_cagr
        diff_str = f"{diff:+.2%}"
    else:
        diff_str = "---"
    
    print(f"{name:<40} {ib_str:<12} {val_str:<12} {diff_str:<12}")

print("=" * 80)
print("\nNote: IB data uses 2020-01-01 start date, validation may use different dates")
