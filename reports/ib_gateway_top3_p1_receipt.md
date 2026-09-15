# IB Gateway top-3 p1 receipt

Implementation commit: `b42dd16693352ddff7577005f393bf2113c3e004`

## Deterministic acceptance proof

Exact command run from the repository root:

```sh
python3 -m pytest backend/tests/test_ib_gateway_state_guard.py backend/tests/test_ib_gateway_health_check.py backend/tests/test_ib_gateway_dormancy_enforcement.py -q
```

Result: `10 passed` (exit 0).

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

The worker-test precondition repair is committed at
`967acf5543e70c1ab6e9945949868e4177458a27`; this receipt follows that repair
and retains the final durable producer's exact success markers.
