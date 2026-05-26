"""Rebalance-frequency model shared by the API and the schedulers.

Strategies declare their native cadence only as prose in their description
("weekly rebalancing", "rebalanced quarterly", ...). This module turns that into
a structured frequency, derives a portfolio's effective cadence from its
constituents, and decides whether a given allocation is due for a rebalance.
"""

from __future__ import annotations

from datetime import datetime, timezone

# Canonical cadences and their interval in days. Ordered fastest -> slowest.
FREQUENCY_DAYS: dict[str, int] = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "quarterly": 90,
}

# Choices the user may store on an allocation. "follow" resolves to the
# portfolio's native cadence; "manual" disables auto-rebalancing.
ALLOC_FREQUENCY_CHOICES: frozenset[str] = frozenset(
    {"follow", "manual", *FREQUENCY_DAYS.keys()}
)

DEFAULT_STRATEGY_FREQUENCY = "monthly"


def infer_strategy_frequency(description: str | None) -> str:
    """Best-effort cadence from a strategy's free-text description."""
    text = (description or "").lower()
    # Check slowest-named keyword first so "rebalanced quarterly" doesn't match "weekly".
    if "quarterly" in text:
        return "quarterly"
    if "monthly" in text:
        return "monthly"
    if "weekly" in text:
        return "weekly"
    if "daily" in text:
        return "daily"
    return DEFAULT_STRATEGY_FREQUENCY


def strategy_frequency_map() -> dict[str, str]:
    """name -> native frequency for every catalog strategy."""
    try:
        from quiver_signals import QuiverSignals  # repo root

        meta = QuiverSignals.get_all_strategies() or {}
    except Exception:
        meta = {}
    out: dict[str, str] = {}
    if isinstance(meta, dict):
        for name, m in meta.items():
            desc = m.get("description") if isinstance(m, dict) else None
            out[name] = infer_strategy_frequency(desc)
    return out


def portfolio_native_frequency(strategy_names: list[str]) -> str:
    """A portfolio's native cadence = the fastest of its constituents, so every
    strategy is refreshed at least as often as it needs."""
    if not strategy_names:
        return DEFAULT_STRATEGY_FREQUENCY
    fmap = strategy_frequency_map()
    freqs = [fmap.get(n, DEFAULT_STRATEGY_FREQUENCY) for n in strategy_names]
    # Fastest = smallest interval in days.
    return min(freqs, key=lambda f: FREQUENCY_DAYS.get(f, FREQUENCY_DAYS[DEFAULT_STRATEGY_FREQUENCY]))


def resolve_frequency(chosen: str | None, native: str) -> str:
    """Map a stored allocation choice to a concrete cadence (or 'manual')."""
    c = (chosen or "follow").strip().lower()
    if c == "follow" or c not in ALLOC_FREQUENCY_CHOICES:
        return native
    return c


def is_due(last: datetime | None, frequency: str, *, now: datetime | None = None) -> bool:
    """True if an allocation on `frequency` should rebalance now.

    `frequency` is a concrete cadence (already resolved); 'manual' is never due.
    A small slack lets a daily-scheduled run fire a 'daily' cadence even if the
    previous run was ~23h ago.
    """
    if frequency == "manual":
        return False
    if frequency not in FREQUENCY_DAYS:
        return True
    if last is None:
        return True
    now = now or datetime.now(timezone.utc)
    # Normalise naive timestamps (DB stores UTC-naive) to aware for subtraction.
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    elapsed_days = (now - last).total_seconds() / 86400.0
    threshold = FREQUENCY_DAYS[frequency] - 0.25  # slack for scheduler jitter
    return elapsed_days >= threshold
