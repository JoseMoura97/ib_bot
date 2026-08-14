# P2 gateway visibility — independent gate receipt

This receipt records the read-only P2 predicates rerun on 2026-08-14. No image
rebuild, service restart, deployment, migration, or live gateway connection was
performed.

## Durable backend-suite gate — PASS

Command:

```sh
test "$(tr -d '\\n' < /home/servidor/Desktop/cursor-projects/conductor/logs/durable/state/c7d39af0-7859-4b60-a00f-508a0705e847.status)" = 0
rg -F '197 passed, 17 skipped, 348 warnings in 62.59s (0:01:02)' reports/p2_backend_suite_verified_20260814.log
rg -F 'Result=success ExecMainStatus=0' reports/p2_backend_suite_verified_20260814.log
```

Literal output:

```text
197 passed, 17 skipped, 348 warnings in 62.59s (0:01:02)
runjob[job-3585705]: unit=rj-job-3585705-3585705 systemd-run_rc=0 Result=success ExecMainStatus=0
durable_status=0
```

The atomic status is exactly `0`; the durable suite therefore has zero failed
tests.

## Ancestry gate — PASS

Command:

```sh
git merge-base --is-ancestor b05d0211abc02ed5ffebd961177a46d274d377ec main
git merge-base --is-ancestor b05d0211abc02ed5ffebd961177a46d274d377ec origin/main
git rev-parse HEAD
git rev-parse origin/main
```

Literal output/exit evidence:

```text
b05d021_ancestor_main=0
b05d021_ancestor_origin_main=0
HEAD=c1ba28a0b4b27fa72b76588745d655cd21307761
origin_main=c1ba28a0b4b27fa72b76588745d655cd21307761
```

`b05d0211abc02ed5ffebd961177a46d274d377ec` (`Expose IB gateway connection
outages`) is an ancestor of both checked refs. The P2 implementation paths
(`test_ib_gateway_connection_visibility.py`, `ib_worker.py`, `live.py`, and
`alerting.py`) are unchanged between that commit and `HEAD` (zero exit from
`git diff --quiet b05d021..HEAD -- <those paths>`).

## Gateway-visibility gate — PASS

The committed test file contains exactly these five cases:

```text
test_healthy_gateway_state_is_exposed_by_live_status
test_forced_connect_failure_is_visible_within_one_poll
test_outage_past_injected_threshold_alerts_exactly_once
test_outage_before_injected_threshold_does_not_alert
test_recovery_resets_connection_counters_and_outage_alert_state
```

Ground-truth command (the API image's source root is `/app`, so the test path
is `backend/tests/...`):

```sh
docker compose exec -T api python3 -m pytest -q backend/tests/test_ib_gateway_connection_visibility.py
```

Literal terminal result:

```text
.....                                                                    [100%]
visibility_pytest_exit=0
```

## Durable action-contract gate — PASS

Contract `aa236c8d-81f9-46fe-9947-e5e4f96571ac` is already measured for the
durable suite rerun. Its machine-readable predicate was checked with:

```sql
SELECT (measured IS NOT NULL)::text || '|' || surprise::text ||
       '|' || categorical_violation::text || '|' || (measured->>'exit_code') ||
       '|' || (measured->>'passed') || '|' || (measured->>'skipped') ||
       '|' || (measured->>'atomic_status') || '|' ||
       (measured->>'artifact_exists')
FROM action_contracts
WHERE id='aa236c8d-81f9-46fe-9947-e5e4f96571ac'::uuid;
```

Literal output:

```text
true|false|false|0|197|17|0|true
```

This means the measurement exists; no surprise or categorical violation was
recorded; exit and atomic status are zero; the 197-pass/17-skipped result and
the promised artifact are present.
