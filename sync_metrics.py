"""
Sync metrics from validation results to plot_data.json.
This fixes incorrect CAGR/Sharpe values while keeping real IB equity curves.
"""
import json
from pathlib import Path
from datetime import datetime

plot_path = Path(".cache/plot_data.json")
validation_path = Path(".cache/last_validation_results.json")
backup_path = Path(".cache/backups/plot_data_pre_sync.json")

# Load both files
plot_data = json.loads(plot_path.read_text(encoding="utf-8"))
validation_data = json.loads(validation_path.read_text(encoding="utf-8"))

print("=" * 80)
print("Syncing metrics from validation results to plot_data.json")
print("=" * 80)

# Backup current plot_data
backup_path.parent.mkdir(parents=True, exist_ok=True)
backup_path.write_text(json.dumps(plot_data, indent=2), encoding="utf-8")
print(f"[OK] Backup saved to {backup_path}")

# Sync metrics for each strategy
synced = 0
for strategy_name in plot_data.get("strategies", {}):
    val_strat = validation_data.get("strategies", {}).get(strategy_name, {})
    plot_strat = plot_data["strategies"][strategy_name]
    
    if val_strat:
        old_cagr = plot_strat.get("cagr", 0)
        old_sharpe = plot_strat.get("sharpe", 0)
        
        # Get metrics from validation (already in percentage for CAGR)
        new_cagr = val_strat.get("cagr", 0)  # e.g., 30.59 for 30.59%
        new_sharpe = val_strat.get("sharpe", 0)
        new_max_dd = val_strat.get("max_drawdown", 0)
        
        # Update plot_data with correct metrics
        plot_strat["cagr"] = new_cagr
        plot_strat["sharpe"] = new_sharpe
        plot_strat["max_drawdown"] = new_max_dd
        
        print(f"{strategy_name:<45} CAGR: {old_cagr:>8.2f} -> {new_cagr:>8.2f}")
        synced += 1
    else:
        print(f"{strategy_name:<45} [SKIP] Not in validation results")

# Update metadata
plot_data["metrics_source"] = "validation_results"
plot_data["metrics_synced_at"] = datetime.now().isoformat()

# Save updated plot_data
plot_path.write_text(json.dumps(plot_data, indent=2), encoding="utf-8")

print("=" * 80)
print(f"[OK] Synced metrics for {synced} strategies")
print(f"[OK] Saved to {plot_path}")
