"""Unit tests for api_caution.confirm_or_abort gating."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure repo-root modules are importable.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api_caution import (  # noqa: E402
    CautionAbort,
    confirm_or_abort,
    estimate_calls,
)


def test_estimate_calls_basic():
    assert estimate_calls(n_tickers=100, n_strategies=10, source="ib") == 100
    assert estimate_calls(n_tickers=100, n_strategies=10, source="ib", calls_per_ticker=3) == 300
    assert estimate_calls(n_tickers=100, n_strategies=10, source="cache_only") == 0


def test_auto_proceed_under_warn(tmp_path):
    # 500 IB calls is below the 1.5k warn — should pass silently.
    confirm_or_abort(
        estimated_calls=500,
        source="ib",
        yes=False,
        reason="unit-test",
        audit_log_path=tmp_path / "audit.log",
    )
    assert (tmp_path / "audit.log").exists()


def test_warn_band_requires_yes_when_non_tty(tmp_path, monkeypatch):
    # 3k IB calls is between warn (1.5k) and block (5k) — non-TTY w/o yes -> abort.
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(CautionAbort):
        confirm_or_abort(
            estimated_calls=3_000,
            source="ib",
            yes=False,
            reason="unit-test",
            audit_log_path=tmp_path / "audit.log",
        )


def test_warn_band_passes_with_yes(tmp_path):
    # Same scenario but explicit yes — proceeds.
    confirm_or_abort(
        estimated_calls=3_000,
        source="ib",
        yes=True,
        audit_log_path=tmp_path / "audit.log",
    )


def test_above_block_requires_yes_and_env(tmp_path, monkeypatch):
    # 8k IB calls > 5k block. yes=True alone is NOT enough.
    monkeypatch.delenv("ALLOW_LARGE_API_RUN", raising=False)
    with pytest.raises(CautionAbort):
        confirm_or_abort(
            estimated_calls=8_000,
            source="ib",
            yes=True,
            audit_log_path=tmp_path / "audit.log",
        )

    monkeypatch.setenv("ALLOW_LARGE_API_RUN", "1")
    # Now it should succeed.
    confirm_or_abort(
        estimated_calls=8_000,
        source="ib",
        yes=True,
        audit_log_path=tmp_path / "audit.log",
    )


def test_cache_only_never_blocks(tmp_path):
    confirm_or_abort(
        estimated_calls=10_000_000,
        source="cache_only",
        yes=False,
        audit_log_path=tmp_path / "audit.log",
    )


def test_budget_override(tmp_path):
    # Override block to a very low value — should reject even small runs.
    with pytest.raises(CautionAbort):
        confirm_or_abort(
            estimated_calls=200,
            source="ib",
            budget_warn=10,
            budget_block=100,
            yes=True,
            audit_log_path=tmp_path / "audit.log",
        )
