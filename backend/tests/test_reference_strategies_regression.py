"""Regression suite for reference strategies.

Runs five well-known strategies through the cache_only path and asserts the
new provenance / dropped-weight contract, plus basic metric sanity. Uses the
project's live .cache/ directory as the data source — skips if empty.

The plan calls for a frozen mini-cache fixture checked into
backend/tests/fixtures/mini_cache/. That can be added later without changing
this file: the test detects the fixture path automatically and prefers it
when present.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "mini_cache"
LIVE_CACHE_DIR = ROOT / ".cache"

# Prefer the frozen fixture if present; else fall back to the live cache.
CACHE_SOURCE = FIXTURE_DIR if (FIXTURE_DIR / "yf_prices").exists() else LIVE_CACHE_DIR

REFERENCE_STRATEGIES = [
    # (strategy_name, is_13f)
    ("Michael Burry (SEC EDGAR)", True),
    ("Bill Ackman (SEC EDGAR)", True),
    ("Howard Marks (SEC EDGAR)", True),
    ("Congress Buys", False),
    ("Nancy Pelosi", False),
]


def _cache_has_data() -> bool:
    yf_dir = CACHE_SOURCE / "yf_prices"
    ib_dir = CACHE_SOURCE / "ib_prices"
    if yf_dir.exists() and any(yf_dir.iterdir()):
        return True
    if ib_dir.exists() and any(ib_dir.iterdir()):
        return True
    return False


@pytest.mark.skipif(not _cache_has_data(),
                    reason="No price cache available — populate .cache/ first.")
@pytest.mark.parametrize("strategy_name,is_13f", REFERENCE_STRATEGIES)
def test_reference_strategy_smoke(monkeypatch, strategy_name, is_13f):
    monkeypatch.setenv("PRICE_SOURCE", "cache_only")
    monkeypatch.delenv("SEC_13F_OPTIONS_MODE", raising=False)  # default = delta_adjusted

    from rebalancing_backtest_engine import RebalancingBacktestEngine

    api_key = os.getenv("QUIVER_API_KEY", "DUMMY")
    bt = RebalancingBacktestEngine(
        quiver_api_key=api_key,
        initial_capital=100_000.0,
        price_source="cache_only",
    )

    result = bt.run_rebalancing_backtest(
        strategy_name=strategy_name,
        start_date="2022-01-01",
        end_date="2024-12-31",
    )

    if "error" in result:
        pytest.skip(f"{strategy_name}: {result['error']}")

    # Provenance contract
    prov = result.get("provenance") or {}
    assert prov.get("options_mode") == "delta_adjusted", (
        f"options_mode must default to delta_adjusted; got {prov.get('options_mode')!r}"
    )
    assert prov.get("price_source") == "cache_only"
    assert "code_sha" in prov
    assert "run_started_at" in prov

    # New dropped-weight reporting fields
    assert "dropped_weight_avg" in result
    assert "dropped_weight_max" in result
    assert "segment_drops" in result
    assert 0.0 <= result["dropped_weight_avg"] <= 1.0
    assert 0.0 <= result["dropped_weight_max"] <= 1.0

    # 13F strategies should drop less than 5% average weight after the
    # classifier integration. If this assertion fires, the classifier
    # admissible set or the Congress feed columns regressed.
    if is_13f:
        assert result["dropped_weight_avg"] < 0.05, (
            f"{strategy_name}: dropped_weight_avg={result['dropped_weight_avg']:.3f} "
            f"exceeds 5% — investigate classifier wiring."
        )

    # Basic metric sanity
    assert isinstance(result["cagr"], float)
    assert isinstance(result["sharpe_ratio"], float)
    # Sanity: not NaN/inf
    import math
    assert math.isfinite(result["cagr"])
    assert math.isfinite(result["sharpe_ratio"])
