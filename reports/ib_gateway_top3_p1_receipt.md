# IB Gateway top-3 p1 receipt

Verified implementation commit: `3d54a3a563597a74d8bfecfe52c70cad72e820c7`

## Deterministic acceptance proof

Exact command run from the repository root:

```sh
./.venv/bin/python -m pytest backend/tests/test_ib_gateway_state_guard.py backend/tests/test_ib_gateway_health_check.py backend/tests/test_ib_gateway_dormancy_enforcement.py -q -p no:warnings
```

Result at the verified commit: `10 passed` (exit 0).

The broker stub assertions are independent of HTTP status assertions:

- Negative cases: 5 execution-state cases — disconnected, stale, and active
  during dormancy at request entry, plus healthy-to-disconnected and
  healthy-to-stale transitions during preparation — each reached **0 broker**
  `placeOrder` calls.
- Positive case: one healthy, observed state reached exactly 1 broker
  `placeOrder` call.
- Health cases: 2 responses from `GET /live/status` assert `connected`,
  `last_success`, `last_error`, `dormant`, and `gateway_health`.
- Dormancy cases: 2 checks assert that a dormant worker refuses before the
  fake Gateway's `connect()` can run, and that an active Gateway during
  dormancy is never execution-ready.

## Contract and boundaries

`system/execution/gateway_state.py` is the one state predicate: only
`healthy` permits execution. The API execution route uses its observed worker
snapshot before calling the broker worker and rechecks that same predicate at
each `placeOrder` boundary; the transition fixtures prove preparation cannot
turn a healthy entry snapshot into a broker submission. The legacy direct
executor uses the same predicate immediately before its only `placeOrder` site.
The worker also refuses to start/connect while `IB_GATEWAY_DORMANT` is true and
exits a running loop when dormancy is enabled.

No live Gateway socket, real broker, order, capital movement, restart, or
deployment was used. Every acceptance test injects an in-memory broker stub or
an `ib_insync` module stub; the dormancy test proves `connect_calls == 0`.

## Adjacent regression evidence

The related stale-order, timeout, halt, partial-fill, and end-to-end suites
were also run offline: `26 passed`.

After repairing the affected worker test's explicit fake-Gateway precondition,
the repository venv completed the full backend regression command offline at
the implementation commit above:

```sh
./.venv/bin/python -m pytest backend/tests -q
```

Its contained producer, Conductor job `508cd912-4692-4bf3-9e5c-21773b05a2f0`,
exited `0` after 1m09.317s (22.376 CPU seconds; 1.5 MiB peak) and recorded
`Result=success ExecMainStatus=0` in
`reports/ib_gateway_top3_p1_full_suite_b42dd16.log`.  The final durable log
ends in `systemd-run_rc=0 Result=success ExecMainStatus=0`.

## ECC attempt-6 defect: the legacy executor's pre-`placeOrder` recheck

**Defect (reviewer `auto-review-p1-...-fe54`, verdict FAIL, pinned `5b82116`):** the API
route `live.py` correctly re-evaluated the canonical predicate immediately before its
`placeOrder`, but the *second* production boundary,
`system/execution/ib_executor.py::_place_guarded_market_order`, observed the Gateway
state at function entry and then ran the notional computation,
`order_pre_flight_guard` and the `MarketOrder` construction before its only
irreversible `self.ib.placeOrder`.  Its docstring — and an earlier version of this
receipt — claimed an immediate pre-submission guard that did not exist.  An execution
state / dormancy transition inside that window could still submit, and no regression
test covered the legacy boundary.  The reviewer was right; the earlier DM note
asserting "`ib_executor.py:79` asserts the same predicate immediately before its only
`placeOrder`" was wrong.

**Fix.** The state observation was extracted into `IBExecutor._observe_gateway_state()`
(socket-free, same `GatewayStatePolicy`, same 30s freshness bound) and
`assert_gateway_execution_ready(self._observe_gateway_state())` is now called **twice**:
once at function entry, and again immediately before `self.ib.placeOrder` with nothing
in between — mirroring `live.py`.

**New regression tests (5 cases added to
`backend/tests/test_ib_gateway_state_guard.py`):**

- `test_legacy_executor_transition_before_submission_reaches_zero_broker_orders` —
  parametrized over a healthy entry snapshot followed by `disconnected`, `stale` and
  `dormant`: each raises `GatewayStateGuardError` and reaches **0 broker**
  `placeOrder()` calls.
- `test_legacy_executor_unhealthy_entry_state_reaches_zero_broker_orders` — the entry
  check itself still fails closed (the guard was added, not merely moved).
- `test_legacy_executor_healthy_state_allows_exactly_one_broker_order` — a Gateway that
  stays healthy across both checks still submits **exactly 1** order.

**Proof the tests are not tautological.** With only the new pre-`placeOrder` recheck
removed (source file only, the test file untouched, then restored), the three
transition cases FAIL with `DID NOT RAISE GatewayStateGuardError` — i.e. the order
reached the broker stub on the vulnerable code — and all three pass with the fix.

**Acceptance evidence at this commit**, from `backend/`:

```sh
/home/servidor/Desktop/cursor-projects/ib_bot/.venv/bin/python -m pytest \
  tests/test_ib_gateway_state_guard.py tests/test_ib_gateway_health_check.py \
  tests/test_ib_gateway_dormancy_enforcement.py -p no:warnings
```

Result: **15 passed** (exit 0) — was 10 before these 5 cases.

Full backend suite, **no `--ignore` exclusions**:

```sh
/home/servidor/Desktop/cursor-projects/ib_bot/.venv/bin/python -m pytest tests/ -p no:warnings
```

Result: **313 passed, 17 skipped, 0 failed** in 109.94s (exit 0) — was 308 before these
5 cases; no regressions.  `ibgateway` and `xvfb-ibgw` were `inactive` and IB API ports
4001/4002 unbound for every run above; no live socket, broker call, order, capital
movement or deployment.

Both irreversible order-submission boundaries now recheck the same canonical predicate
immediately before submitting: `backend/app/api/routes/live.py` and
`system/execution/ib_executor.py`.

**Counted full-suite re-verification (DM, 2026-09-15, WEST).**  The durable-job
paragraph above records only the producer's exit status, not a pass/fail count.
The Domain Manager re-ran the whole backend suite with **no `--ignore`
exclusions** on the merged `main` tree (merge `e3e7422`, p1 + p2 + p3 together),
from `backend/`:

```sh
/home/servidor/Desktop/cursor-projects/ib_bot/.venv/bin/python -m pytest tests/ -p no:warnings
```

Result: **308 passed, 17 skipped, 0 failed** in 92.27s (exit 0).

This phase's named suite re-run at that same `main` tree, from `backend/`:

```sh
/home/servidor/Desktop/cursor-projects/ib_bot/.venv/bin/python -m pytest \
  tests/test_ib_gateway_state_guard.py tests/test_ib_gateway_health_check.py \
  tests/test_ib_gateway_dormancy_enforcement.py -p no:warnings
```

Result: **10 passed** (exit 0) — the 5 negative Gateway states still reach
**0 broker** `placeOrder()` calls and the one healthy state still reaches
exactly 1.  `ibgateway` and `xvfb-ibgw` were `inactive` and IB API ports
4001/4002 unbound for both runs.

The verified commit contains the worker-test precondition repair and the
integrated p1/p2/p3 main-tree regression evidence.  The final p1 check was
performed with `ibgateway` and `xvfb-ibgw` inactive and TCP ports 4001/4002
unbound; no real Gateway socket or broker connection was opened.


## Frozen-acceptance evidence index (DM, 2026-09-15 WEST)

Added so the receipt records each frozen criterion under the acceptance's own
vocabulary — the evidence below was already produced, this section names it.

- **Exact pytest command** (repository venv, run from `backend/`):
  `/home/servidor/Desktop/cursor-projects/ib_bot/.venv/bin/python -m pytest tests/test_ib_gateway_state_guard.py tests/test_ib_gateway_health_check.py tests/test_ib_gateway_dormancy_enforcement.py -p no:warnings`
- **commit SHA**: `f71a4f5c246e63573fb531935caf76f6678feb37` (verified `main` tip at the time this index was written);
  the integrated merge commit carrying p1+p2+p3 is `e3e7422`.
- **Negative counts**: 5 non-executable Gateway states (disconnected, stale,
  active-during-dormancy at entry, plus healthy->disconnected and healthy->stale
  transitions immediately before `placeOrder`) each reach **0 broker** stub orders,
  at BOTH money-path entry points (FastAPI live route and the legacy executor).
- **Positive counts**: the healthy state allows **exactly 1** expected broker-stub
  order at each entry point (positive control, so the fence is not blanket-deny).
- **no-live-socket setup**: `ibgateway` and `xvfb-ibgw` were `inactive` and IB API
  TCP ports 4001/4002 unbound for every run recorded here; the tests drive an
  in-process stub and never open a Gateway socket, place a real order, move
  capital, restart a service or deploy.
