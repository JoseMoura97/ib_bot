# Dashboard End-User QA Script

Assumes the web app is reachable at `http://localhost:8080`.

## 1) `/dashboard`

- Load page → confirm it calls plot data and renders the chart.
- Use Search to find strategies; toggle several checkboxes → chart overlays update.
- Click each preset button (Top 5 CAGR, Congress, etc.) → selection changes.
- Click Reload → data refetch works.
- Click Update Data → confirm progress bar moves and finishes; refresh doesn’t break UI; chart updates afterward.
- Enable/disable a strategy from the UI (if present) → confirm it persists after reload.

## 2) `/dashboard/metrics`

- Confirm metrics table loads (no errors) and matches expected cached validation/plot data.
- Refresh the page and confirm it’s stable.

## 3) `/strategies`

- Search for a strategy → select it → verify config JSON loads.
- Toggle enabled on/off → reload page → confirm it persisted.
- Edit config JSON (make a small, valid change) → Save config → reload → confirm saved.
- Try invalid JSON → confirm UI shows a validation error and does not save.

## 4) `/portfolios`

- Create a new portfolio (name/description/settings) → confirm it appears in list after refresh.
- Add 2–3 strategies, set weights, click Normalize weights, then Save strategies.
- Reload portfolio → confirm weights and enabled flags persisted.
- Switch mode (holdings_union vs nav_blend) if supported → save → reload to confirm.

## 5) `/allocations`

- Select the portfolio you created.
- Create a paper allocation (small amount) → submit → confirm it appears in history and totals update.
- Repeat with another allocation note → confirm history ordering.

## 6) `/runs`

- Confirm list loads.
- If empty, create one via the UI (or API) then confirm it appears.

## 7) `/runs/[id]`

- Open a run → confirm it polls until terminal and then loads results.
- Validate: equity curve renders, metrics show, and tables populate.

## 8) `/paper` (paper trading)

- Create/select a paper account.
- Fund it → confirm cash/equity updates.
- Place a simple BUY then SELL (small qty) → confirm:
  - Orders list updates
  - Fills list updates
  - Positions reflect the trades
- Select a portfolio → Preview rebalance → verify legs look sensible.
- Execute rebalance → confirm positions/fills update and no negative cash surprises.

## 9) `/live` (live trading UI, safe mode)

- Connect to IB (host/port) → confirm status and accounts load.
- Load account snapshot → confirm balances/positions render.
- Use Preview with strict limits → confirm preview returns legs.
- Verify Execute is blocked unless `ENABLE_LIVE_TRADING=1` and confirm checkbox is ticked.

## 10) `/dashboard/legacy` + `/dashboard/guide`

- Legacy iframe loads and refresh button works.
- Guide page renders.

## “Ready for live trading” acceptance

- Paper rebalance works repeatedly (10+ cycles) with no drift/inconsistency.
- Live preview matches expectation and is repeatable day-to-day.
- Execution has: market-hours guard, idempotency, fill tracking, partial-failure handling, per-ticker limits, circuit breaker.
- Monitoring exists: logs, DB audit trail, and a clear “stop trading now” switch.
