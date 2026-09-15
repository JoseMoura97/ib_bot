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
