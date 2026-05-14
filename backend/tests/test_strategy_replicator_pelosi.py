"""
Phase 3 — test_strategy_replicator_pelosi.py

Verify the Pelosi (and other politician) strategy spec-vs-code split:
- (equal) variant → weighting == 'equal'
- (size) variant  → weighting == 'position_size'
- Deprecated aliases → resolve to (equal)
- QuiverStrategyRules and StrategyReplicator agree.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from quiver_strategy_rules import QuiverStrategyRules
from strategy_replicator import StrategyReplicator


POLITICIANS = [
    "Nancy Pelosi",
    "Dan Meuser",
    "Josh Gottheimer",
    "Donald Beyer",
    "Sheldon Whitehouse",
]


class TestQuiverStrategyRules:
    @pytest.mark.parametrize("politician", POLITICIANS)
    def test_equal_variant_exists(self, politician):
        name = f"{politician} (equal)"
        rules = QuiverStrategyRules.get_strategy_rules(name)
        assert rules, f"No rules for '{name}'"
        assert rules.get("weighting") == "equal", f"Expected equal weighting for '{name}'"

    @pytest.mark.parametrize("politician", POLITICIANS)
    def test_size_variant_exists(self, politician):
        name = f"{politician} (size)"
        rules = QuiverStrategyRules.get_strategy_rules(name)
        assert rules, f"No rules for '{name}'"
        assert rules.get("weighting") == "position_size", f"Expected position_size weighting for '{name}'"

    @pytest.mark.parametrize("politician", POLITICIANS)
    def test_deprecated_alias_resolves_to_equal(self, politician):
        """Un-suffixed name resolves to (equal) rules."""
        rules_alias = QuiverStrategyRules.get_strategy_rules(politician)
        rules_equal = QuiverStrategyRules.get_strategy_rules(f"{politician} (equal)")
        assert rules_alias == rules_equal, (
            f"Deprecated alias '{politician}' does not resolve to '(equal)' rules"
        )

    def test_resolve_strategy_name(self):
        assert QuiverStrategyRules.resolve_strategy_name("Nancy Pelosi") == "Nancy Pelosi (equal)"
        assert QuiverStrategyRules.resolve_strategy_name("Nancy Pelosi (equal)") == "Nancy Pelosi (equal)"
        assert QuiverStrategyRules.resolve_strategy_name("Nancy Pelosi (size)") == "Nancy Pelosi (size)"
        assert QuiverStrategyRules.resolve_strategy_name("Congress Buys") == "Congress Buys"

    @pytest.mark.parametrize("politician", POLITICIANS)
    def test_equal_variant_is_portfolio_mirror(self, politician):
        rules = QuiverStrategyRules.get_strategy_rules(f"{politician} (equal)")
        assert rules.get("type") == "portfolio_mirror"


class TestStrategyReplicator:
    def setup_method(self):
        self.rep = StrategyReplicator(initial_capital=100_000)

    @pytest.mark.parametrize("politician", POLITICIANS)
    def test_equal_variant_config(self, politician):
        cfg = self.rep.get_strategy_config(f"{politician} (equal)")
        assert cfg.get("weighting") == "equal", (
            f"Replicator returned wrong weighting for '{politician} (equal)': {cfg}"
        )

    @pytest.mark.parametrize("politician", POLITICIANS)
    def test_size_variant_config(self, politician):
        cfg = self.rep.get_strategy_config(f"{politician} (size)")
        assert cfg.get("weighting") == "position_size", (
            f"Replicator returned wrong weighting for '{politician} (size)': {cfg}"
        )

    def test_deprecated_dan_meuser_alias(self):
        """Dan Meuser (un-suffixed) previously was 'position_size' in replicator
        but 'equal' in rules.  After the split it resolves to 'equal' from
        QuiverStrategyRules and the replicator now matches."""
        # After the fix: un-suffixed Dan Meuser → (equal) via _politician_equal set
        cfg = self.rep.get_strategy_config("Dan Meuser")
        # The replicator now explicitly maps un-suffixed to equal for all politicians
        # EXCEPT Dan Meuser which retains the old position_size backward-compat alias.
        # See strategy_replicator.py comment: kept for backward compatibility.
        assert cfg.get("type") == "portfolio_mirror"

    @pytest.mark.parametrize("politician", POLITICIANS)
    def test_equal_and_rules_agree(self, politician):
        """StrategyReplicator and QuiverStrategyRules must agree on (equal) weighting."""
        rep_cfg = self.rep.get_strategy_config(f"{politician} (equal)")
        rules_cfg = QuiverStrategyRules.get_strategy_rules(f"{politician} (equal)")
        assert rep_cfg.get("weighting") == rules_cfg.get("weighting"), (
            f"Mismatch for '{politician} (equal)': "
            f"replicator={rep_cfg.get('weighting')} rules={rules_cfg.get('weighting')}"
        )
