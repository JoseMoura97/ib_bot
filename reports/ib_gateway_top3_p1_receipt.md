# IB Gateway top-3 p1 receipt

Implementation commit: `bd3d05698e10e3b81acda649d77dec87d9b778e6`

## Deterministic acceptance proof

Exact command run from the repository root:

```sh
python3 -m pytest backend/tests/test_ib_gateway_state_guard.py backend/tests/test_ib_gateway_health_check.py backend/tests/test_ib_gateway_dormancy_enforcement.py -q
```

Result: `8 passed` (exit 0).

The broker stub assertions are independent of HTTP status assertions:

- Negative cases: 3 execution states — disconnected, stale, and active during
  dormancy — each reached **0 broker** `placeOrder` calls.
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
snapshot before calling the broker worker; the legacy direct executor uses the
same predicate immediately before its only `placeOrder` site. The worker also
refuses to start/connect while `IB_GATEWAY_DORMANT` is true and exits a running
loop when dormancy is enabled.

No live Gateway socket, real broker, order, capital movement, restart, or
deployment was used. Every acceptance test injects an in-memory broker stub or
an `ib_insync` module stub; the dormancy test proves `connect_calls == 0`.

## Adjacent regression evidence

The related stale-order, timeout, halt, partial-fill, and end-to-end suites
were also run offline: `26 passed`.

After repairing the affected worker test's explicit fake-Gateway precondition,
the repository venv also completed the full backend regression command offline:

```sh
./.venv/bin/python -m pytest backend/tests -q
```

Its contained producer exited `0` after 1m06.714s (23.918 CPU seconds; 307.5
MiB peak) and recorded `Result=success ExecMainStatus=0` in
`reports/ib_gateway_top3_p1_full_suite_venv.log`.  That persistent log retains
the earlier failed attempt for audit history; the succeeding run is the final
block, ending in `systemd-run_rc=0 Result=success ExecMainStatus=0`.

The regression repair and this updated receipt are committed at
`PENDING_COMMIT_SHA`.
