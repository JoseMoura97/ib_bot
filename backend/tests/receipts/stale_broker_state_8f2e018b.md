# Receipt — p3-stale-broker-state (roadmap 5144dfda, plan 8f2e018b)

**Source SHA:** `121d0f077917559817cada12aed21579c2b8f8d4`
(branch `conductor/phase-p3-stale-broker-state-ca69`, repo `ib_bot`)

**Supersedes:** a prior attempt at `c9fed17b079cd5de0b0077d0044a96b4e843bf3b`
was reviewed and **FAILED** by the independent ECC reviewer (attempt
`7e1c637b-4003-4cc9-b62a-6dad46e5e5e8`, verdict recorded 2026-09-02 13:45
WEST against receipt commit `fd45fea`). See "Round 2" below for the gap it
found and the fix that closes it. A prior fix is not credit unless re-proved
at the current source revision — this receipt is written against the new SHA
above, not the superseded one.

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

## Round 2 — ECC reviewer FAIL, and the cancellation-race fix

The reviewer's independent, no-network reproduction: the caller times out at
20ms while `reqAllOpenOrders()` is blocked; once released, the *same enqueued
closure* went on to call `placeOrder` (`placeOrder=1`). Root cause, confirmed
in `backend/app/services/ib_worker.py:74-84`: `_IbWorker.call()` enqueues
`(fn, fut)` and waits via `fut.result(timeout=timeout)`. When that outer wait
times out, the HTTP caller gives up and moves on — but nothing stopped the
worker thread from continuing to run `fn` (which is the entire `_execute`
closure, including the `ib.placeOrder` call) to completion. Round 1's fix
only closed exceptions raised *inside* `_execute`'s own
`ib.reqAllOpenOrders()` call; it did not touch this outer, caller-side
timeout path at all.

Fix, `backend/app/services/ib_worker.py`:
- `_CancelToken` — a `threading.Event`-backed abandonment flag, deliberately
  independent of `concurrent.futures.Future.cancel()`, which refuses to
  cancel a `Future` once it is `RUNNING` and therefore cannot express "the
  caller gave up" for a task that is already mid-execution (blocked inside a
  broker call) — exactly this bug's shape.
- `call()` abandons the token when `fut.result(timeout=...)` raises
  `TimeoutError`.
- `_run()` skips a still-queued task outright if its token is already
  abandoned before dequeue (cheap early exit for the queued-but-not-started
  case).
- New `call_is_cancelled()` (module-level) / `is_active_call_abandoned()`
  (instance method) expose whether the closure currently running on the
  worker thread has an abandoned caller.

Fix, `backend/app/api/routes/live.py`: `_execute` now calls
`call_is_cancelled()` immediately before the only `ib.placeOrder()` call site
in the per-leg loop and refuses with `409 reconciliation required` if the
caller already timed out — the same "fence immediately before the
irreversible action" placement as the pre-flight notional guard right above
it.

## Test file

`backend/tests/test_stale_broker_order_state.py` — 6 cases:

1. `test_broker_timeout_blocks_placement_and_surfaces_reconciliation` —
   `reqAllOpenOrders` raises a broker timeout → 5xx, "reconciliation
   required" surfaced, `place_calls == 0`.
2. `test_stale_open_order_blocks_placement_and_surfaces_reconciliation` —
   `reqAllOpenOrders` returns one non-terminal ("Submitted") order for
   the account → 409, "reconciliation required" surfaced,
   `place_calls == 0`.
3. `test_reconciled_broker_state_permits_exactly_one_placement`
   (parametrized `clear` / `terminal`, 2 cases) — three sequential attempts
   on one stub instance: (a) timeout → blocked, 0 placements; (b) stale
   non-terminal order → blocked, 0 placements; (c) broker confirms either
   no open orders or the earlier order resolved to `Filled` → the ONLY
   attempt that succeeds, `place_calls == 1` at the end of the sequence.
4. **`test_call_ib_timeout_blocks_placeorder_from_abandoned_call`** (new,
   Round 2) — reproduces the reviewer's exact race against the REAL
   `_IbWorker`/`call_ib` machinery (not a synchronous stub): `fn` is
   dequeued by the worker thread and blocks inside a fake
   `reqAllOpenOrders()`; the caller's `call_ib(fn, timeout=0.05)` times out
   and gives up (`entered_block.wait()` proves `fn` was genuinely already
   running, i.e. the race is real, not a no-op skip); the test then releases
   the block and asserts `place_calls == []`. No socket, no `ib_insync`
   network call — `_worker._ib` is pointed at an in-memory fake broker
   object, reset to `None` in `finally` so the module-level singleton isn't
   left polluted for other tests.
5. **`test_execute_refuses_placeorder_when_call_is_cancelled`** (new, Round
   2) — wiring check that `_execute`'s `placeOrder` call site actually
   consults `call_is_cancelled()` (a real 60s+ outer timeout is impractical
   in a unit test, since `execute_timeout = legs*per_leg_timeout + 60s` is
   hardcoded): with `call_is_cancelled()` forced `True`, asserts `409` +
   `place_calls == 0`.

Cases 1-3 and 5 go through the real `/live/rebalance/execute` route via
FastAPI's `TestClient` with `call_ib` monkeypatched to a synchronous stub
broker; case 4 exercises the real `_IbWorker`/`call_ib` machinery directly.
No IB Gateway socket is opened anywhere in the file. Verified:
`grep -n "IB()\|\.connect(\|socket\|127.0.0.1\|localhost"
backend/tests/test_stale_broker_order_state.py` matches only docstring
prose, not executable code — **0 real Gateway connections, 0 real broker
calls** across all 6 tests.

## Focused pytest output

```
$ cd backend && python3 -m pytest tests/test_stale_broker_order_state.py -v -p no:warnings
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/servidor/Desktop/cursor-projects/ib_bot/.worktrees/phase-p3-stale-broker-state-ca69
configfile: pytest.ini
plugins: asyncio-1.4.0, anyio-4.13.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 6 items

tests/test_stale_broker_order_state.py ......                            [100%]

============================== 6 passed in 0.58s ===============================
```

**0 failures.** Re-ran 3× consecutively (with `test_ib_worker.py` run both
before and after) to check for singleton-state flakiness from the new
threading-based race test — stable every time, 0 pollution.

## Regression check (no fail-open reintroduced elsewhere)

Ran every test file that exercises the live-rebalance execute path, the
`_IbWorker` singleton, or any `reqAllOpenOrders`-touching broker stub, same
worktree/SHA:

```
$ python3 -m pytest tests/test_stale_broker_order_state.py tests/test_ib_worker.py \
    tests/test_live_order_guard_bypass.py tests/test_live_call_ib_timeout.py \
    tests/test_live_partial_fill.py tests/test_live_halt_mid_rebalance.py \
    tests/test_live_idempotency.py tests/test_live_account_whitelist.py \
    tests/test_live_max_order_pct_nlv.py tests/test_api_smoke_workflows.py \
    tests/test_e2e_full_cycle.py tests/test_paper_rebalance_cycles.py \
    tests/test_ib_gateway_connection_visibility.py -v -p no:warnings
...
collected 57 items
...
============================== 57 passed in 3.47s ===============================
```

57/57 passed, 0 failures, 0 regressions from either fix. Also ran the full
backend suite (`pytest tests/ --ignore=...` the 4 known pre-existing
environment-gap files per `.cursorrules`: missing repo-root imports ×3,
missing `psycopg` ×1) — clean, 0 failures, only pre-existing unrelated
skips.

## Scope discipline

No IB Gateway socket was opened, no order was placed, no cap/policy value
was changed, and no service was restarted at any point while producing
this receipt — the only broker in play across every test in this suite is
an in-process synchronous Python stub.
