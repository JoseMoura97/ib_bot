"""
API-caution gate for high-volume IB / yfinance runs.

Used by run_all_backtests.py, generate_plot_data.py, and any future script
that may hit external market-data APIs in bulk. Refuses to silently launch
a multi-thousand-call run.

Tiers (per source):
    estimated_calls <= budget_warn        → log only, proceed.
    budget_warn < calls <= budget_block   → print warning, prompt y/N on a
                                            TTY. Non-TTY requires yes=True.
    estimated_calls > budget_block        → require yes=True AND env
                                            ALLOW_LARGE_API_RUN=1, else
                                            CautionAbort.

A structured line is appended to .cache/api_caution.log for every decision.
"""

from __future__ import annotations

import getpass
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class CautionAbort(RuntimeError):
    """Raised when the caution gate refuses a run."""


# Per-source default budgets, calibrated against the actual TWS API ceilings:
# - reqHistoricalData hard limit is 60 requests / rolling 600 s = 6 req/min
#   sustained. At that pace, 5k calls already takes ~14 hours; 24k takes 67 h.
# - Web/REST and yfinance are far more forgiving.
# These thresholds reflect "time you can afford to spend" rather than "calls
# the API will technically accept" — see https://interactivebrokers.github.io
# /tws-api/historical_limitations.html.
_DEFAULT_BUDGETS = {
    "ib":         {"warn":  1_500, "block":  5_000},
    "yfinance":   {"warn": 10_000, "block": 60_000},
    "auto":       {"warn":  1_500, "block":  5_000},   # treat as IB-equivalent
    "cache_only": {"warn":  10**9, "block": 10**9},     # never blocks
}


def _budgets_for(source: str, *, override_warn: Optional[int] = None,
                 override_block: Optional[int] = None) -> tuple[int, int]:
    d = _DEFAULT_BUDGETS.get(source, _DEFAULT_BUDGETS["ib"])
    warn = int(override_warn) if override_warn is not None else d["warn"]
    block = int(override_block) if override_block is not None else d["block"]
    return warn, block


def estimate_calls(*, n_tickers: int, n_strategies: int, source: str,
                   calls_per_ticker: int = 1) -> int:
    """
    Rough estimate. For backtest pipelines a ticker is normally fetched once
    per run regardless of how many strategies reference it, so n_strategies
    is informational (logged but not multiplied). Callers with a better model
    can pass calls_per_ticker.
    """
    if source == "cache_only":
        return 0
    return max(0, int(n_tickers) * max(1, int(calls_per_ticker)))


def _audit_log(path: Path, payload: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, sort_keys=True) + "\n")
    except Exception:
        pass


def confirm_or_abort(*, estimated_calls: int, source: str,
                     budget_warn: Optional[int] = None,
                     budget_block: Optional[int] = None,
                     yes: bool = False,
                     reason: str = "",
                     audit_log_path: Optional[Path] = None) -> None:
    """
    Gate a high-volume API run. Returns silently on approval, raises
    CautionAbort otherwise.

    Parameters
    ----------
    estimated_calls : int
        Pre-flight estimate of upstream API calls this run will make.
    source : str
        One of "ib", "yfinance", "auto", "cache_only".
    yes : bool
        Pre-confirmation (e.g. from a --yes flag). Required for non-TTY
        approval in the warn band, and required (plus ALLOW_LARGE_API_RUN=1)
        for approval above the block budget.
    """
    warn, block = _budgets_for(source, override_warn=budget_warn,
                               override_block=budget_block)
    audit_path = audit_log_path or Path(".cache/api_caution.log")
    base_payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": source,
        "estimated_calls": int(estimated_calls),
        "budget_warn": warn,
        "budget_block": block,
        "reason": reason,
        "user": _safe_user(),
    }

    if estimated_calls <= warn:
        _audit_log(audit_path, {**base_payload, "decision": "auto_proceed"})
        logger.info(
            "api_caution: %d calls (source=%s) under warn budget %d — proceeding.",
            estimated_calls, source, warn,
        )
        return

    if estimated_calls > block:
        if yes and os.environ.get("ALLOW_LARGE_API_RUN", "").strip() == "1":
            _audit_log(audit_path, {**base_payload, "decision": "approved_override"})
            print(
                f"api_caution: APPROVED override — {estimated_calls} calls (source={source}) "
                f"exceeds block budget {block}. Proceeding because --yes and "
                f"ALLOW_LARGE_API_RUN=1.",
                file=sys.stderr,
            )
            return
        _audit_log(audit_path, {**base_payload, "decision": "blocked_over_budget"})
        raise CautionAbort(
            f"Estimated {estimated_calls} {source} calls exceeds block budget "
            f"{block}. To proceed: re-run with --yes and ALLOW_LARGE_API_RUN=1 "
            f"in the environment."
        )

    # Warn band: warn < calls <= block
    print(
        f"\n⚠️  api_caution: {estimated_calls} {source} calls estimated "
        f"(warn={warn}, block={block}).{(' Reason: ' + reason) if reason else ''}",
        file=sys.stderr,
    )

    if yes:
        _audit_log(audit_path, {**base_payload, "decision": "approved_flag"})
        print("api_caution: proceeding (--yes).", file=sys.stderr)
        return

    if not sys.stdin.isatty():
        _audit_log(audit_path, {**base_payload, "decision": "blocked_non_tty"})
        raise CautionAbort(
            f"Non-interactive session: refusing {estimated_calls} {source} "
            f"calls without --yes. Re-run with --yes to confirm."
        )

    print(f"Proceed with {estimated_calls} {source} API calls? [y/N]: ",
          end="", file=sys.stderr, flush=True)
    try:
        ans = input().strip().lower()
    except EOFError:
        ans = ""
    if ans in {"y", "yes"}:
        _audit_log(audit_path, {**base_payload, "decision": "approved_interactive"})
        print("api_caution: proceeding.", file=sys.stderr)
        return

    _audit_log(audit_path, {**base_payload, "decision": "declined_interactive"})
    raise CautionAbort(
        f"User declined run of {estimated_calls} {source} calls."
    )


def _safe_user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"
