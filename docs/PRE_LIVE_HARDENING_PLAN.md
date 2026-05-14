---
name: ib bot pre-live hardening
overview: "Three parallel audits of the IB Bot uncovered material bugs in both the live execution path and the backtest methodology. The strong recommendation is: do NOT flip ENABLE_LIVE_TRADING=true yet. Below is a prioritized Pre-Live Hardening plan: critical safety fixes, methodology corrections, and a calibration plan for paper trading before any real-money go-live."
todos:
  - id: phase1-fill-sync
    content: "Phase 1: Rewrite fill-synchronization to wait for terminal status, abort remaining legs on timeout, call reqGlobalCancel"
    status: pending
  - id: phase1-halt-midrebal
    content: "Phase 1: Cooperative halt check between legs + persistent halt state in DB"
    status: pending
  - id: phase1-idempotency
    content: "Phase 1: Mandatory Idempotency-Key header (server-side reject + frontend send) + IN_PROGRESS TTL sweeper"
    status: pending
  - id: phase1-account-whitelist
    content: "Phase 1: Server-side account_id whitelist against IB.managedAccounts()"
    status: pending
  - id: phase1-tests
    content: "Phase 5: Tests for the 4 Phase 1 fixes (idempotency, halt, partial fill, account whitelist)"
    status: pending
  - id: phase2-pct-nlv
    content: "Phase 2: Enforce LIVE_MAX_ORDER_PCT_NLV on execute path"
    status: pending
  - id: phase2-daily-pnl
    content: "Phase 2: Rewrite daily P&L circuit breaker using IB.accountSummary RealizedPnL"
    status: pending
  - id: phase2-audit-detail
    content: "Phase 2: GET /live/audit/{id} with full request+orders payload"
    status: pending
  - id: phase2-stuck-rows
    content: "Phase 2: Celery beat job to reconcile stuck IN_PROGRESS rows"
    status: pending
  - id: phase3-lookahead
    content: "Phase 3: Fix aggregate congress lookahead bias (ReportDate before TransactionDate everywhere)"
    status: pending
  - id: phase3-exec-lag
    content: "Phase 3: Add EXECUTION_OFFSET_DAYS=1 default in backtest engine"
    status: pending
  - id: phase3-sharpe
    content: "Phase 3: Standard Sharpe formula across rebalancing_backtest_engine, run_all_backtests, portfolio_math"
    status: pending
  - id: phase3-pelosi-spec
    content: "Phase 3: Resolve Pelosi rules-vs-code drift; split into Pelosi (equal) and Pelosi (size)"
    status: pending
  - id: phase3-costs
    content: "Phase 3: Default transaction_cost_bps=5.0 + slippage model"
    status: pending
  - id: phase3-missing-tkr
    content: "Phase 3: Default MISSING_TICKER_POLICY=cash"
    status: pending
  - id: phase3-walkforward
    content: "Phase 3: Walk-forward + block bootstrap research scripts"
    status: pending
  - id: phase4-sector
    content: "Phase 4: Remove Ticker+Weight short-circuit for sector-targeted strategies"
    status: pending
  - id: phase4-insider
    content: "Phase 4: Implement insider_score from SEC Form 4 OR disable strategy"
    status: pending
  - id: phase4-house-filter
    content: "Phase 4: Tolerant House chamber filter everywhere"
    status: pending
  - id: phase4-ticker-len
    content: "Phase 4: Drop len>7 ticker filter; use char regex"
    status: pending
  - id: phase6-paper-calib
    content: "Phase 6: 5 paper rebalance cycles on EPYC, log fill rates/slippage/disconnects"
    status: pending
  - id: go-live
    content: Live at 1% allocation for 1 week, then ramp 5% -> 20% -> full
    status: pending
isProject: false
---


# IB Bot — Pre-Live Hardening Plan

## Verdict

**Do not go live yet.** The audits found three categories of issues that, individually, would not block live trading; collectively they create unacceptable tail risk on a real account:

- **Live path:** four CRITICAL bugs that can split a basket, leak duplicate orders, or fail to halt mid-rebalance.
- **Backtest path:** lookahead bias on aggregate congress strategies, a non-standard Sharpe formula, zero-default transaction costs, and no walk-forward / bootstrap.
- **Strategy code:** rules-vs-code spec drift on Pelosi/Meuser, sector-weight short-circuit, weak insider selection.

Pelosi's "underperformance" in our backtest is **most likely real** — but the backtest is not the right instrument to draw that conclusion yet, because the methodology has known biases that go in both directions.

---

## Pre-Live Checklist (must all be GREEN before flipping `ENABLE_LIVE_TRADING=true`)

1. CRITICAL bugs section below: all fixed and tested.
2. `LIVE_MAX_ORDER_PCT_NLV` enforced on `/live/rebalance/execute` (not just checklist).
3. Mandatory `Idempotency-Key` header — frontend (`LiveAccountsClient.tsx`) sends it; backend rejects executes without one.
4. Server-side `account_id` allowlist against `managedAccounts()` from IB.
5. `API_KEY` set in production `.env`; nginx never exposes `api:8000` publicly.
6. Telegram alerting tokens set; `send_halt_alert` and `send_rebalance_alert` tested end-to-end.
7. Paper account on EPYC has run **at least 5 successful rebalance cycles** with the corrected code (calibration period).
8. `live_max_daily_loss_pct` rewritten to use `IBClient.accountSummary()` `RealizedPnL` / equity, not signed-quantity heuristic.
9. Persistent halt state in DB (so `POST /live/halt` survives restart).
10. Restricted ticker list defined (no penny stocks under $1, no leveraged/inverse ETFs) — server-side rejection.
11. First live run is **manual only**, with `allocation_amount` ≤ 5% of NLV. No Celery beat live job.

---

## Phase 1 — CRITICAL live-path fixes (block live trading)

### 1. Fill-synchronization rewrite

[backend/app/api/routes/live.py:699-737](backend/app/api/routes/live.py)

Current loop waits 10s, accepts non-terminal status as "ok", continues to next leg. Fix:

- Wait for terminal status (`Filled`, `Cancelled`, `ApiCancelled`, `Inactive`, `Rejected`) up to a configurable per-leg timeout (default 60s).
- On non-terminal at timeout: **abort remaining legs**, call `ib.reqGlobalCancel()`, mark audit `INCOMPLETE`, send Telegram alert.
- Bound the entire `_execute` call by `len(legs) × per_leg_timeout + buffer` instead of fixed 30s in `call_ib(..., timeout=30.0)`.

### 2. Cooperative halt mid-rebalance

[backend/app/api/routes/live.py](backend/app/api/routes/live.py) `_execute` inner loop

Re-check `settings.trading_halt` between legs. If set, call `ib.reqGlobalCancel()` and abort. Persist halt state to a DB row in `system_state` table so `POST /live/halt` survives an API restart.

### 3. Mandatory idempotency

[backend/app/api/routes/live.py:596-606](backend/app/api/routes/live.py) and [frontend/app/live/LiveAccountsClient.tsx:317-321](frontend/app/live/LiveAccountsClient.tsx)

- Server: 400 if `Idempotency-Key` header missing on execute.
- Frontend: generate `crypto.randomUUID()` per execute click and send as header.
- TTL on `IN_PROGRESS` rows: a sweeper resets stuck rows >10 min old to `FAILED`.

### 4. `account_id` whitelist

[backend/app/api/routes/live.py:674-676](backend/app/api/routes/live.py)

On startup, cache `IB.managedAccounts()`. Reject any execute whose `body.account_id` not in that list. Add an env-level allowlist (`LIVE_ALLOWED_ACCOUNTS=U15721390`) for additional belt-and-suspenders.

---

## Phase 2 — HIGH live-path fixes

5. Enforce `LIVE_MAX_ORDER_PCT_NLV` on execute (server-side cap, ignores body overrides).
6. Rewrite daily P&L circuit breaker to read `IB.accountSummary()` `RealizedPnL` + `UnrealizedPnL`, instead of the broken signed-quantity sum at [live.py:434-437](backend/app/api/routes/live.py).
7. New endpoint `GET /live/audit/{id}` that returns full `request` + `orders` JSON for forensic replay.
8. Stuck `IN_PROGRESS` reconciliation: Celery beat job every 5 min that flips rows older than 10 min to `FAILED` with note.
9. Health check (`/health`) validates IB connectivity, not just process up.

---

## Phase 3 — Backtest methodology fixes

### 10. Lookahead bias on aggregate congress strategies

[quiver_engine.py:498-517](quiver_engine.py) — Aggregate `congress` (Congress Buys, etc.) uses `TransactionDate` before `ReportDate`, giving the backtest information the market couldn't have seen. Fix: prefer `ReportDate` for **all** congress paths, not just `name_pattern` ones.

```python
preferred = ["ReportDate", "TransactionDate", "Date", "LastUpdate"]  # ALL congress
```

### 11. Execution lag

[rebalancing_backtest_engine.py](rebalancing_backtest_engine.py) `_date_range_mask` — Backtest enters at the **same-day close** of the signal date (zero-latency assumption). Fix: shift the first applicable return to the **next trading day open** using `exchange_calendars` already imported in `market_calendar.py`. Add a configurable `EXECUTION_OFFSET_DAYS` (default 1).

### 12. Standard Sharpe ratio

[rebalancing_backtest_engine.py:613-621](rebalancing_backtest_engine.py) and [run_all_backtests.py:121-126](run_all_backtests.py) — Replace mixed CAGR/daily-vol formula with:

```python
sharpe = (np.mean(daily_returns - rf_daily) / np.std(daily_returns)) * np.sqrt(252)
```

Same fix in [backend/app/services/portfolio_math.py:76-82](backend/app/services/portfolio_math.py).

### 13. Resolve Pelosi spec drift

[quiver_strategy_rules.py:51-58](quiver_strategy_rules.py) says `weighting: equal`; [strategy_replicator.py:205-212](strategy_replicator.py) forces `position_size`. Pick one and label clearly. Recommendation: keep both as separate strategies (`Pelosi (equal)` and `Pelosi (size)`), since both are defensible — but stop pretending the result matches Quiver's published Pelosi.

### 14. Default transaction costs > 0

[backend/app/services/portfolio_backtest.py:21-41](backend/app/services/portfolio_backtest.py) — Default `transaction_cost_bps=5.0` (5 bps round-trip is conservative). Add a slippage model proportional to inverse-ADV for sub-$1B market caps.

### 15. Missing-ticker policy

[rebalancing_backtest_engine.py:448-453](rebalancing_backtest_engine.py) — Default `MISSING_TICKER_POLICY=cash` everywhere (currently `renormalize` for non-cache, which inflates surviving names). Survivorship bias quantification should be a known number, not a hidden one.

### 16. Walk-forward + bootstrap

Add a research script `research/validation/walk_forward.py` that splits the sample into K=5 chronological folds, refits weights/parameters per fold, and reports OOS Sharpe + CI. Plus block bootstrap (1000 resamples, 30-day blocks) for Sharpe confidence intervals.

---

## Phase 4 — Strategy logic corrections

17. **Sector Weighted DC Insider** ([strategy_replicator.py:313-323](strategy_replicator.py)) — Remove the `Ticker`+`Weight` short-circuit for sector-targeted strategies. The sector logic should always run if the strategy type demands it.

18. **Insider Purchases** ([strategy_replicator.py:255-261](strategy_replicator.py)) — `insider_score` is rarely present in raw data, so selection silently degenerates to "first 10 tickers". Either implement the score from SEC Form 4 or disable the strategy until done.

19. **House chamber filter inconsistency** ([quiver_engine.py:738-741](quiver_engine.py) vs `:479-482`) — Use the tolerant `isin(["House", "Representatives", ...])` everywhere.

20. **Ticker length filter** ([rebalancing_backtest_engine.py:217-218](rebalancing_backtest_engine.py)) — Drop the `len > 7` rule (kills valid `BRK.B`-style symbols silently). Replace with explicit invalid-character regex.

21. **Disable for first live cycle**: Insider Purchases (broken selection), Sector Weighted DC Insider (sector logic bypassed). Re-enable per-strategy after Phase 4 fixes.

---

## Phase 5 — Tests (block live trading)

Add to [backend/tests/](backend/tests/):

- `test_live_idempotency.py` — same key replayed returns identical response, zero duplicate IB calls.
- `test_live_halt_mid_rebalance.py` — halt during multi-leg execute aborts remaining legs and calls `reqGlobalCancel`.
- `test_live_partial_fill.py` — `Submitted` forever scenario stops the basket.
- `test_live_account_whitelist.py` — wrong account → 400.
- `test_live_max_order_pct_nlv.py` — execute over env cap → 403.
- `test_live_call_ib_timeout.py` — 30s+ scenario handles in-flight orders correctly.
- `test_backtest_lookahead.py` — synthetic bulk row with `TransactionDate << ReportDate` does not appear in signal until `ReportDate`.
- `test_backtest_execution_lag.py` — first return is next-day, not same-day.
- `test_backtest_sharpe_standard.py` — known series produces textbook Sharpe value.
- `test_strategy_replicator_pelosi.py` — equal-weight branch matches rules file.

Pytest must pass before `ENABLE_LIVE_TRADING=true` in any environment.

---

## Phase 6 — Calibration on paper before live

Even after all the above, run **at least 5 paper rebalance cycles** on EPYC's `betano-workers-vm`-style isolated paper account (port 4003). Record per-cycle:
- Order fill rates and partial-fill counts.
- Slippage vs preview prices.
- Any disconnect/reconnect events.
- Halt/resume drill at least once mid-cycle.

If all 5 cycles pass with no surprises, increase live allocation gradually: 1% → 5% → 20% → full over 4 weekly cycles.

---

## Recommended sequence (calendar)

| Week | Phases | Risk if rushed |
|---|---|---|
| 1 | Phase 1 (CRITICAL live) + Phase 5 (live tests) | Real-money loss on first execute |
| 2 | Phase 2 (HIGH live) + Phase 3.10–3.12 (lookahead/lag/Sharpe) | Wrong daily-loss halt; biased validation numbers |
| 3 | Phase 3.13–3.16 (Pelosi spec / costs / missing-ticker / walk-forward) | Strategy choices based on biased numbers |
| 4 | Phase 4 (strategy logic) + Phase 6 (paper calibration) | Live with strategies that quietly fall back to first-N tickers |
| 5 | Live trading at 1% allocation for 1 week | — |
| 6 | Ramp to 5% if clean | — |
| 7+ | Ramp to full | — |

---

## What NOT to fix before live

- Walk-forward & bootstrap (Phase 3.16) is "nice to have" for confidence in expected returns; not required to safely operate.
- Wash sale prevention, margin calc — only matter at much larger size.
- Fractional shares — keep integer shares for simplicity.

---

## Concrete next action when you confirm

I'll start by implementing **Phase 1 (4 CRITICAL live-path fixes) + Phase 5 tests for those four bugs**. That's the smallest unit that meaningfully reduces the chance of an account-busting incident. Estimated work: 1 focused session.

Want me to proceed with Phase 1 only, or roll Phase 1 + Phase 2 together?
