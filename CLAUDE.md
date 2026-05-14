<!-- claude-md-auto-generated: do not edit manually -->
<!-- regenerate: python3 ~/.claude/scripts/generate-claude-md.py --project ib_bot -->

# ib_bot — Claude Code rules

Imported from Cursor memory. Last generated: 2026-05-10T22:51:40Z
Regenerate after structural rule changes (new/deleted file, alwaysApply change).

## Rule management

To add, edit, or delete rules: edit the `.mdc` files in `.cursor/rules/` directly
(Cursor reads the same files — changes are shared automatically).
After structural changes (new file, deleted file, or alwaysApply change), run:
    python3 ~/.claude/scripts/generate-claude-md.py --project ib_bot

## Always-loaded rules

@.cursorrules
@.cursor/rules/server-portugal-shadow.mdc
@.cursor/rules/server-portugal.mdc
@.cursor/rules/server-setup.mdc

## Supplemental rules

Not auto-loaded. Reference by filename when working on related code,
or ask Claude to read them explicitly.

| File | Description | Triggers |
|------|-------------|----------|
| `.cursor/rules/strategy-replication.mdc` | Strategy replication methodology, backtest engine architecture, and Quiver alignment decisions | `strategy_replicator.py,quiver_engine.py,quiver_strategy_rules.py,quiver_signals.py,rebalancing_backtest_engine.py,generate_plot_data.py,backtest_engine.py` |
