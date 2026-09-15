# IB Gateway top-3 — p2 receipt: malformed IB API response validation

Plan: `4c48535c-a900-470b-b84f-91fdf5d3c228`, phase `p2`.
Roadmap item: `8ae07426-4aa7-42d1-84c2-8ae2a797f0c7` — Unvalidated IB API response parsing.

## Scope traced

Every IB API response parser on the live-trading path (signals → account/positions →
tickers → order placement/execution) in the FastAPI backend:

- `backend/app/api/routes/ib.py`: `_normalize_accounts`, `_managed_accounts`,
  `_accounts_from_account_summary`, `_account_values_for_account`,
  `_positions_for_account`, `_account_values_to_dicts`, `_positions_to_dicts`, `_to_float`.
- `backend/app/api/routes/live.py`: `_to_float`, `_extract_nlv`, `_extract_realized_pnl`,
  `_extract_unrealized_pnl`, `_current_positions_for_account`, `_fetch_live_quotes`
  (ticker/price parsing incl. sanity checks: price<=0, stale quote, wide spread,
  deviation from last close), `_parse_ib_time`, order/execution result parsing in
  `_execute` (`orderStatus`, `fills`, `_execution_to_dict`).
- `backend/app/services/ib_worker.py`: transport layer (`call_ib`), out of scope for
  payload-shape parsing (no response-field access) but exercised indirectly via
  `call_ib` monkeypatches in the new tests.

Root-level `system/execution/ib_executor.py` is a legacy/unused CLI helper not wired
into the FastAPI backend's signals/execution path (confirmed via `grep -rl ib_insync`
across the repo); left out of scope per acceptance's `backend/tests/...` target.

## Finding

The existing parsers were already largely defensive (`getattr(..., None)` + `_to_float`
+ skip-on-`None` patterns throughout), consistent with prior hardening work in this
codebase (`_CancelToken`, `call_try_commit`, `reqAllOpenOrders` reconciliation fence).
No dangerous parsing gap was found where a malformed IB payload could reach
`ib.placeOrder()` — malformed data either raises an `HTTPException` (rejected) before
execution or is silently excluded from the parsed result (safe no-op). This phase adds
the missing **regression-proof test coverage** confirming that invariant, with fixtures
per parser across five categories: missing-key, wrong-type, null/empty, extra-field,
and valid — plus a broker-stub end-to-end proof.

## New test file

`backend/tests/test_ib_api_response_parsing.py` — 60 test cases (parametrized), all
green:

```
$ cd backend && python3 -m pytest tests/test_ib_api_response_parsing.py -q -p no:warnings
............................................................            [100%]
60 passed in <1s>
```

Coverage:
1. `_normalize_accounts` — 7 cases (missing/wrong-type/null-empty/extra-separators/valid).
2. `_managed_accounts` — 5 cases across `managedAccounts()`, `wrapper.accounts`,
   `accountSummary(group="All")` fallback sources.
3. `_account_values_for_account` / `_positions_for_account` — 11 cases, including a
   wrong-type dict-instead-of-list payload proven not to crash `_account_values_to_dicts`.
4. `_extract_nlv` / `_extract_realized_pnl` / `_extract_unrealized_pnl` — parametrized
   across all 3 extractors × 5 fixture categories = 15 cases.
5. `_to_float` (both copies, `ib.py` and `live.py`) — 2 cases covering 8 malformed
   inputs each.
6. `_current_positions_for_account` — 6 cases via a `call_ib` stub exercising the real
   `_positions_for_account` parsing chain.
7. `_fetch_live_quotes` — 9 cases: missing contract, wrong-type price fields, null/empty
   ticker list, null price, extra vendor field ignored, non-iterable `reqTickers()`
   response (fails loudly, never fabricates a quote), price<=0 rejected, stale quote
   rejected, valid quote parses correctly.
8. Broker-stub end-to-end (`FakeBrokerIB.placed_orders`) — 5 cases: 4 malformed
   `reqTickers()` fixtures each asserted to reach **0 broker**-stub `placeOrder()`
   calls and a
   non-2xx response (explicitly excluding the "ib_insync import failed" false-positive
   rejection path), plus 1 valid fixture asserted to place **exactly** the expected
   single order (`BADTICK BUY 100.0` shares for a $10,000 allocation at $100/share).

## Full backend suite (regression check)

```
$ cd backend && python3 -m pytest tests/ -p no:warnings \
    --ignore=tests/test_edgar_13f_fallback.py \
    --ignore=tests/test_plot_data_cache.py \
    --ignore=tests/test_rebalancing_engine_regressions.py \
    --ignore=tests/test_altdata_chain.py
258 passed, 17 skipped in 5.36s
```

(`test_edgar_13f_fallback.py`, `test_plot_data_cache.py`,
`test_rebalancing_engine_regressions.py` have pre-existing repo-root import errors per
`.cursorrules`; `test_altdata_chain.py` has a pre-existing unrelated collection error,
confirmed on the commit this branch is based on — untouched by this phase.)

## Commit

Worktree branch `conductor/phase-p2-43e6`, based on commit `08028c32ffac85e4ba1b361676041fd189dbc4bb`.

## Re-verification after integrating p1 into this branch (2026-09-15, ART)

`conductor/phase-p2-43e6` was merged with `main` at `fc988dc` (the p1 Gateway
state/health/dormancy hardening) so this phase's evidence is measured on the
integrated tree, not on an isolated base.

Exact command re-run from the repository root on the merged tree:

```sh
./.venv/bin/python -m pytest backend/tests/test_ib_api_response_parsing.py -q -p no:warnings
```

Result: `60 passed` (exit 0).  The broker-stub end-to-end cases still reach
**0 broker** `placeOrder()` calls for all 4 malformed `reqTickers()` fixtures
and **exactly 1** order for the valid fixture.

No live Gateway socket, real broker, order, capital movement, restart or
deployment was used: `ibgateway` and `xvfb-ibgw` were `inactive` and IB API
ports 4001/4002 unbound while these tests ran.

## ECC attempt-2 fix: non-finite (NaN/+Inf/-Inf) IB values (2026-09-15, ART)

**Defect (reviewer `auto-review-p2-...-827b`, verdict 19:00 WEST, pinned
`e66cd051`):** `_to_float` (duplicated verbatim in `ib.py`, `live.py`, and
`metrics.py`) parsed `NaN`/`+Inf`/`-Inf` unchanged instead of rejecting them.
A `reqTickers().marketPrice()` of `NaN` (line `live.py:469`, direct
`float(t.marketPrice())`, no finite guard) flowed into `_fetch_live_quotes`'s
own `price = _to_float(...)` check unchanged, since every sanity comparison
after it (`price <= 0`, `price > max_abs_price`, deviation-from-close) is
`False` for `NaN` and therefore never rejects it. With
`LIVE_FRACTIONAL_SHARES=true` and an existing position, `_build_preview`
computed `target_qty = target_value / NaN = NaN`, `delta = NaN - current_qty
= NaN`; the dust-leg skip (`abs(delta) < min_delta`) is `False` for `NaN` so
it never fired, and `side = "BUY" if delta > 0 else "SELL"` defaulted to
`"SELL"` (also `False` for `NaN`) — producing a real leg with `NaN` price and
`NaN` quantity. The shared `order_pre_flight_guard`'s `notional > cap`
checks are likewise `False` for `NaN`, so the last fence before
`ib.placeOrder()` passed it through too.

**Reproduced live before fixing:** built the exact scenario (existing
position + fractional shares + `NaN` `marketPrice()`) against the pre-fix
code (temporarily isolated via `git stash` on only the four source files,
never touching the test file) and confirmed the broker stub recorded
`('BADTICK', 'SELL', nan)` and the app crashed at the `ib_orders` insert on
`NOT NULL constraint failed: ib_orders.quantity` — i.e. the order reached
`ib.placeOrder()` with a `NaN` quantity before any DB-level rejection. Then
restored the fix (`git stash apply` + drop) and re-ran green. This proves
the new regression tests are not tautological — they fail on the vulnerable
code and pass only with the fix.

**Fix (4 files):**
1. `backend/app/api/routes/live.py` `_to_float` — reject non-finite via
   `math.isfinite`; also hardened the `marketPrice()` direct-cast at line
   469 so a raw `NaN`/`Inf` return falls through to the `last`/`close`
   fallback (which is itself now finite-checked) instead of being kept.
2. `backend/app/api/routes/ib.py` `_to_float` — same fix (byte-identical
   duplicate).
3. `backend/app/api/routes/metrics.py` `_to_float` — same fix (byte-identical
   duplicate, including the percent-string branch).
4. `system/execution/order_preflight.py` `order_pre_flight_guard` — added an
   unconditional `math.isfinite` check on `order_notional_usd` /
   `aggregate_notional_usd` before the cap comparisons, so the shared
   last-line-of-defense guard (used by both the FastAPI route and legacy
   executors) fails closed on a non-finite notional regardless of whether
   caps are configured, not just when `_to_float` happens to catch it
   upstream.

**New regression tests (17 cases added, 60 → 77 total, all in
`backend/tests/test_ib_api_response_parsing.py`):**
- `TestToFloat.test_non_finite_wrong_type_is_rejected_not_passed_through` —
  parametrized across all 3 `_to_float` copies (`ib`, `live`, `metrics`):
  raw `float('nan')`/`float('inf')`/`float('-inf')` and their string forms
  (`"nan"`, `"NaN"`, `"inf"`, `"-inf"`, `"Infinity"`) all → `None`.
- `TestFetchLiveQuotes.test_wrong_type_non_finite_market_price_excluded_not_passed_through`
  — `marketPrice()` returning NaN/+Inf/-Inf never produces a quote.
- `TestBrokerStubZeroOrdersOnNonFinitePrice.test_non_finite_market_price_yields_zero_broker_orders`
  — full `/live/rebalance/execute` path with `LIVE_FRACTIONAL_SHARES=true`
  and an existing `BADTICK` position (reproducing the reviewer's exact
  NaN-SELL-leg shape) for NaN, +Inf, -Inf: asserts non-2xx response, no
  "ib_insync import failed" false-positive, and `fake_ib.placed_orders ==
  []`.
- `TestOrderPreFlightGuardRejectsNonFiniteNotional` — unit-level proof the
  shared guard rejects non-finite `order_notional_usd`/`aggregate_notional_usd`
  unconditionally, plus a valid-finite-within-caps control case.

**Acceptance evidence:**

```sh
$ cd backend && python3 -m pytest tests/test_ib_api_response_parsing.py -q -p no:warnings
........................................................................ [ 93%]
.....                                                                    [100%]
77 passed in <2s>   # exit 0; all 60 pre-existing cases still green
```

Full backend suite on this tree (p1-integrated, post-fix):

```sh
$ cd backend && python3 -m pytest tests/ -p no:warnings \
    --ignore=tests/test_edgar_13f_fallback.py \
    --ignore=tests/test_plot_data_cache.py \
    --ignore=tests/test_rebalancing_engine_regressions.py \
    --ignore=tests/test_altdata_chain.py
285 passed, 17 skipped in 53.91s
```

(285/17 here vs. the DM-reported main-integrated 291/16 baseline — this
worktree's HEAD (`e66cd05`) predates whatever later commits on `main`
account for that delta; `test_altdata_chain.py`'s pre-existing unrelated
collection error was independently re-confirmed on this tree, still
untouched by this phase.)

No live Gateway socket, real broker, order, capital movement, restart, merge
to `main`, or deployment was used. Work stayed entirely inside
`.worktrees/phase-p2-43e6` on branch `conductor/phase-p2-43e6`.
