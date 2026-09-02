# Receipt — p3-stale-broker-state (roadmap 5144dfda, plan 8f2e018b)

**Source SHA:** `cace8024952cf8e8628a6c9d24776fd4d52dd23e`
(branch `conductor/phase-p3-stale-broker-state-ca69`, repo `ib_bot`)

**This markdown is not the proof.** Per the ECC reviewer's own note: it runs
the frozen oracle and reproduces independently rather than trusting prose.
Everything below is written to be re-executed, not just read — every command
block is the literal command that was actually run to produce the output
directly beneath it, at the SHA above, in this worktree.

**Supersedes:**
- `c9fed17b` (Round 1) — **FAILED** by ECC attempt `7e1c637b`, verdict
  recorded 2026-09-02 13:45 WEST against receipt commit `fd45fea`.
- `121d0f07` (Round 2) — **FAILED** by ECC attempt `a2334753`, verdict
  recorded 2026-09-02 14:05 WEST against receipt commit `8124f0b`.

A prior fix is not credit unless re-proved at the current source revision —
this receipt is written against `cace8024`, not either superseded SHA. See
"Round 2" and "Round 3" below for what each reviewer found and the fix that
closed it.

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

## Round 3 — ECC reviewer FAIL #2 (TOCTOU in Round 2's own fix), and the atomic-gate fix

Reviewer verdict FAIL, attempt `a2334753` @ `8124f0bd`, 2026-09-02 14:05
WEST. Round 2's fence in `live.py` was itself a check-then-act race:
`call_is_cancelled()` (a **read**) at line 936, `ib.placeOrder()` (the
**act**) at line 950 — two separate steps with a live gap between them. The
reviewer's no-network reproduction: the closure passed the check with
`cancelled == False`, paused immediately after, the caller's `call_ib(...)`
expired at 50ms and marked the token abandoned, and releasing the closure
let the order go out anyway. No amount of moving the check closer to the
call removes this class of bug — only making the transition atomic does.

Fix, `backend/app/services/ib_worker.py` — `_CancelToken` now exposes a
single atomic transition instead of a read (`is_abandoned`) plus a separate
write (`abandon`) on independent code paths:

- `abandon()` (caller thread, called when `fut.result(timeout=...)` raises)
  and `try_commit()` (worker thread, called immediately before the
  irreversible action, with **no branching** between a `True` return and the
  action actually executing) both acquire the token's own `threading.Lock`.
- Whichever runs first under the lock wins, and there are exactly two
  outcomes:
  - **abandon wins** — `try_commit()` (called after) finds `_abandoned`
    already `True` and returns `False` → **0** `placeOrder` calls, and the
    original caller sees a plain, clean `TimeoutError` (nothing happened,
    safe as an ordinary timeout).
  - **commit wins** — `_committed` is set before the lock is released, so
    the subsequent `abandon()` call sees it and returns `False` →
    `_IbWorker.call()` raises an explicit `503 reconciliation required`
    instead of a clean `TimeoutError`. The order is **not** undone — it is
    surfaced as non-terminal/ambiguous, exactly the phase's contract
    ("o estado fique visivel e nao-terminal, nunca sucesso nem nada
    aconteceu").
  - Once abandoned, the flag is sticky, so later legs in the same basket
    also refuse to commit — no *further* orders once the caller has given
    up, even if an earlier leg already committed.
- `call_try_commit()` (module-level) / `_IbWorker.try_commit_active_call()`
  replace `call_is_cancelled()` as the gate at `live.py`'s only
  `ib.placeOrder()` call site. `call_is_cancelled()` is kept, but now
  explicitly documented as read-only/unsafe for gating an irreversible
  action.
- `try_commit_active_call()` returns `True` when there is no active call
  context (i.e. `call_ib` itself was replaced by a synchronous stub, as most
  of this repo's existing tests do) — there is no caller-timeout race to
  protect against when there is no timeout machinery in play at all. Without
  this, every pre-existing test that stubs `call_ib` synchronously
  (`test_live_order_guard_bypass.py`, sections 1-3 below, etc.) would have
  regressed to always-refuse. This was caught and fixed before commit by
  actually running the full regression sweep, not asserted from theory.

## Test file

`backend/tests/test_stale_broker_order_state.py` — 9 cases:

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
4. **`test_call_ib_timeout_wins_blocks_placeorder`** (Round 3) — timeout-wins
   branch, forced deterministically (not timing-dependent): `fn` blocks
   inside a fake `reqAllOpenOrders()`; the caller's `call_ib(fn,
   timeout=0.05)` times out and abandons WHILE `fn` is still blocked, i.e.
   strictly before `fn` can ever reach `try_commit()`. Releasing the block
   lets `fn` call `try_commit()`, which must return `False` — asserts
   `commit_results == [False]`, `place_calls == []`, and the caller sees a
   plain `TimeoutError`.
5. **`test_call_ib_commit_wins_surfaces_reconciliation_required`** (Round 3)
   — commit-wins branch, forced deterministically: `fn` calls
   `try_commit()` FIRST (must succeed — nothing has abandoned it yet,
   proven by `assert ok` inside `fn`), and only then, inside the
   now-committed `placeOrder` call itself, blocks past the caller's
   timeout. Asserts `call_ib(...)` raises `HTTPException(503)` with
   "reconciliation required" in the detail (never a clean timeout), then
   releases the block and asserts `place_calls == [1]` — exactly one
   placement, proving the order really did go out and was not silently
   discarded.
6. **`test_cancel_token_abandon_before_commit_blocks_action`** /
   **`test_cancel_token_commit_before_abandon_surfaces_ambiguity`** (Round
   3) — pure unit tests of `_CancelToken` itself, no threading, no timing:
   both call orderings are asserted directly, including that a later
   `try_commit()` on an already-abandoned token still refuses.
7. **`test_execute_refuses_placeorder_when_call_try_commit_denies`**
   (updated for Round 3) — wiring check that `_execute`'s `placeOrder` call
   site consults the ATOMIC `call_try_commit()`, not the old read-only
   `call_is_cancelled()` (a real 60s+ outer timeout is impractical in a unit
   test, since `execute_timeout = legs*per_leg_timeout + 60s` is
   hardcoded): with `call_try_commit()` forced to return `False`, asserts
   `409` + `place_calls == 0`.

Cases 1-3 and 7 go through the real `/live/rebalance/execute` route via
FastAPI's `TestClient` with `call_ib` monkeypatched to a synchronous stub
broker; cases 4-6 exercise the real `_IbWorker`/`call_ib`/`_CancelToken`
machinery directly. No IB Gateway socket is opened anywhere in the file.
Verified: `grep -n "IB()\|\.connect(\|socket\|127.0.0.1\|localhost"
backend/tests/test_stale_broker_order_state.py` matches only docstring
prose, not executable code — **0 real Gateway connections, 0 real broker
calls** across all 9 tests.

## Focused pytest output — re-run this exact command to verify

```
$ cd backend && python3 -m pytest tests/test_stale_broker_order_state.py -v -p no:warnings
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/servidor/Desktop/cursor-projects/ib_bot/.worktrees/phase-p3-stale-broker-state-ca69
configfile: pytest.ini
plugins: asyncio-1.4.0, anyio-4.13.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 9 items

tests/test_stale_broker_order_state.py .........                         [100%]

============================== 9 passed in 0.84s ===============================
```

**0 failures.** Re-ran 5× consecutively at this exact SHA to check for
threading-timing flakiness in the two forced-race tests — stable every time,
identical `.........` output.

## Regression check (no fail-open, no over-eager fail-closed, reintroduced elsewhere) — re-run this exact command to verify

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
collected 60 items
...
============================== 60 passed in 3.65s ===============================
```

60/60 passed, 0 failures. `test_live_order_guard_bypass.py`'s
`test_allowed_api_order_places_exactly_one_order` in particular is the test
that would have caught the `try_commit_active_call()` fail-closed-by-default
mistake described above (it stubs `call_ib` synchronously and expects
exactly 1 `placeOrder` call) — it passes.

Also ran the full backend suite
(`pytest tests/ --ignore=...` the 4 known pre-existing environment-gap files
per `.cursorrules`: missing repo-root imports ×3, missing `psycopg` ×1) —
clean, 0 failures, only pre-existing unrelated skips.

## Scope discipline

No IB Gateway socket was opened, no order was placed, no cap/policy value
was changed, and no service was restarted at any point while producing
this receipt — the only broker in play across every test in this suite is
an in-process synchronous Python stub.
