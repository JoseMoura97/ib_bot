# Alt-data PIT tamper-evidence receipt — 2026-08-12

Database migration `0013_altdata_correction_audit_nonce` replaces the former
forgeable `active` session setting with a correction nonce that must match an
append-only audit row for the exact snapshot, old/new values, and PostgreSQL
transaction.  The corrections ledger itself now rejects `UPDATE` and `DELETE`.

## DB negative tests

```text
$ UPDATE altdata_snapshots SET n_rows=n_rows+1 WHERE id=(SELECT min(id) FROM altdata_snapshots);
ERROR:  altdata_snapshots is append-only; use apply_altdata_snapshot_correction for an audited correction
CONTEXT:  PL/pgSQL function reject_altdata_snapshot_mutation() line 21 at RAISE

$ SET LOCAL ib_bot.altdata_authorized_correction='active'; UPDATE altdata_snapshots SET n_rows=n_rows+1 WHERE id=(SELECT min(id) FROM altdata_snapshots);
ERROR:  altdata_snapshots is append-only; use apply_altdata_snapshot_correction for an audited correction
CONTEXT:  PL/pgSQL function reject_altdata_snapshot_mutation() line 21 at RAISE

$ DELETE FROM altdata_snapshots WHERE id=(SELECT min(id) FROM altdata_snapshots);
ERROR:  altdata_snapshots is append-only; use apply_altdata_snapshot_correction for an audited correction
CONTEXT:  PL/pgSQL function reject_altdata_snapshot_mutation() line 21 at RAISE

$ DELETE FROM altdata_snapshot_corrections WHERE id=(SELECT max(id) FROM altdata_snapshot_corrections);
ERROR:  altdata_snapshot_corrections is append-only
CONTEXT:  PL/pgSQL function reject_altdata_snapshot_correction_mutation() line 3 at RAISE
```

The audited exception path was exercised once with values intentionally left
unchanged.  It wrote `snapshot_id=1`, actor `codex-h4-tamper-evidence`, and a
non-null nonce and transaction id; the snapshot count remained 328.

## Hash-chain verifier

`docker compose exec -T worker python /app/scripts/verify_altdata_chain.py --write-manifest --negative-test --manifest /app/reports/altdata_chain_manifest.json --report /app/reports/altdata_chain_verify.json`

```text
total_days=30
chained_valid_days=30
negative_test_detected=true
top_manifest_hash=1143778e2eb9a2b5dff56eb09a52e63c21c81cca58e366a178ddc6fad9b0346c
negative target=2026-07-28
negative invalid days=2026-07-28 through 2026-08-11 (15 days)
```

The negative verifier copied the table, altered a payload byte on 2026-07-28,
and independently observed invalid manifests for that day and every later day.
