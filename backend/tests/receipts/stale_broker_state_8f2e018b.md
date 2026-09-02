# Receipt — p3-stale-broker-state (roadmap 5144dfda, plan 8f2e018b)

**Source SHA:** `c9fed17b079cd5de0b0077d0044a96b4e843bf3b`
(branch `conductor/phase-p3-stale-broker-state-ca69`, repo `ib_bot`)

## What changed

`backend/app/api/routes/live.py::execute_live_rebalance_core` (`_execute`)
guards the only `ib.placeOrder` call site in the live-rebalance execution
path with an anti-duplicate / stale-state check that lists the account's
open orders at the broker before placing anything new.

Before this phase, that check swallowed **any** exception from
`ib.reqAllOpenOrders()` — including a broker timeout — and silently treated
it as "no open orders", so a hung/erroring broker check **failed open** and
let a new basket race an in-flight/duplicate one. Fixed to fail closed:

- A broker exception while checking order state now raises a `503` with
  `"reconciliation required: could not verify broker order state ..."`
  and never reaches `placeOrder`.
- A non-terminal (stale) open order still outstanding for the account now
  raises a `409` with `"reconciliation required: ... non-terminal
  order(s) at IB; reconcile broker state before executing a new
  rebalance"` and never reaches `placeOrder`.
- Only a subsequent call, after the broker confirms a terminal/matching
  state (no open orders, or the earlier order resolved to a terminal
  status such as `Filled`), is permitted through — exactly once.

Three pre-existing fixture brokers (`test_live_call_ib_timeout.py`,
`test_live_partial_fill.py`, `test_live_halt_mid_rebalance.py`) previously
relied on the swallowed-exception fail-open path implicitly (their stub
`ib` objects had no `reqAllOpenOrders` method at all, so the old code's
bare `except Exception` silently treated the resulting `AttributeError` as
"no open orders"). None of those tests exercise open-order state, so each
was given an explicit `reqAllOpenOrders() -> []` stub to preserve their
prior "no open orders" behaviour under the new fail-closed semantics.

## Test file

`backend/tests/test_stale_broker_order_state.py` — 4 cases (2 fixed +
1 parametrized ×2), all against the real `/live/rebalance/execute` route
via FastAPI's `TestClient`, with `call_ib` monkeypatched to invoke a
synchronous stub broker (`_StaleBrokerStub`) that counts `placeOrder`
and `reqAllOpenOrders` invocations:

1. `test_broker_timeout_blocks_placement_and_surfaces_reconciliation` —
   `reqAllOpenOrders` raises a broker timeout → 5xx, "reconciliation
   required" surfaced, `place_calls == 0`.
2. `test_stale_open_order_blocks_placement_and_surfaces_reconciliation` —
   `reqAllOpenOrders` returns one non-terminal ("Submitted") order for
   the account → 409, "reconciliation required" surfaced,
   `place_calls == 0`.
3. `test_reconciled_broker_state_permits_exactly_one_placement`
   (parametrized `clear` / `terminal`) — three sequential attempts on one
   stub instance: (a) timeout → blocked, 0 placements; (b) stale
   non-terminal order → blocked, 0 placements; (c) broker confirms either
   no open orders or the earlier order resolved to `Filled` → the ONLY
   attempt that succeeds, `place_calls == 1` at the end of the sequence.

No IB Gateway socket is opened anywhere in the test file or in the code
path exercised — `call_ib` is monkeypatched so the FastAPI route body runs
synchronously against `_StaleBrokerStub`, which implements no networking
(`reqAllOpenOrders`/`placeOrder`/`qualifyContracts`/`sleep` are plain
in-memory Python methods). Verified: `grep -n "IB()\|\.connect(\|socket\|127.0.0.1\|localhost"
backend/tests/test_stale_broker_order_state.py` matches only the
docstring's prose, not executable code — **0 real Gateway connections,
0 real broker calls**.

## Focused pytest output

```
$ cd backend && python3 -m pytest tests/test_stale_broker_order_state.py -v -p no:warnings
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/servidor/Desktop/cursor-projects/ib_bot/.worktrees/phase-p3-stale-broker-state-ca69
configfile: pytest.ini
plugins: asyncio-1.4.0, anyio-4.13.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 4 items

tests/test_stale_broker_order_state.py ....                              [100%]

============================== 4 passed in 0.21s ===============================
```

**0 failures.**

## Regression check (no fail-open reintroduced elsewhere)

Ran every test file that exercises the live-rebalance execute path or any
`reqAllOpenOrders`-touching broker stub, same worktree/SHA:

```
$ python3 -m pytest tests/test_stale_broker_order_state.py \
    tests/test_live_order_guard_bypass.py tests/test_live_call_ib_timeout.py \
    tests/test_live_partial_fill.py tests/test_live_halt_mid_rebalance.py \
    tests/test_live_idempotency.py tests/test_live_account_whitelist.py \
    tests/test_live_max_order_pct_nlv.py tests/test_api_smoke_workflows.py \
    tests/test_e2e_full_cycle.py tests/test_paper_rebalance_cycles.py \
    -v -p no:warnings
...
collected 49 items
...
============================== 49 passed in 2.94s ===============================
```

49/49 passed, 0 failures, 0 regressions from the fail-closed change.

## Scope discipline

No IB Gateway socket was opened, no order was placed, no cap/policy value
was changed, and no service was restarted at any point while producing
this receipt — the only broker in play across every test in this suite is
an in-process synchronous Python stub.
