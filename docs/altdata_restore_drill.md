# Alt-data PIT restore drill

The nightly `ib-altdata-backup.timer` stores a PostgreSQL custom-format archive
of `public.altdata_snapshots` in this private repository.  The backup script
keeps fourteen days of archive files in `backups/altdata_snapshots/` and pushes
each committed archive to `origin/main`.

Run the drill against a fresh scratch database.  Do not restore into `ibbot`.

```bash
dump=backups/altdata_snapshots/altdata_snapshots_<timestamp>.dump
scratch=ibbot_altdata_restore_drill
docker exec ib_bot-db-1 dropdb -U ibbot --if-exists "$scratch"
docker exec ib_bot-db-1 createdb -U ibbot "$scratch"
docker exec -i ib_bot-db-1 pg_restore -U ibbot -d "$scratch" < "$dump"
docker exec ib_bot-db-1 psql -U ibbot -d "$scratch" -c \
  "CREATE EXTENSION postgres_fdw; CREATE SCHEMA live; CREATE SERVER live_ibbot FOREIGN DATA WRAPPER postgres_fdw OPTIONS (dbname 'ibbot'); CREATE USER MAPPING FOR ibbot SERVER live_ibbot OPTIONS (user 'ibbot'); IMPORT FOREIGN SCHEMA public LIMIT TO (altdata_snapshots) FROM SERVER live_ibbot INTO live;"
docker exec ib_bot-db-1 psql -U ibbot -d "$scratch" -tAc \
  'SELECT count(*) FROM (SELECT source, as_of_date, n_rows, content_hash FROM public.altdata_snapshots EXCEPT SELECT source, as_of_date, n_rows, content_hash FROM live.altdata_snapshots) d'
docker exec ib_bot-db-1 dropdb -U ibbot "$scratch"
```

The two `EXCEPT` directions must both be zero: the command above checks rows in
the restored copy absent from the live copy; repeat with the SELECT sides
reversed to check the live copy has no extra row.

## Out-of-band correction path

The running API, worker, and beat use `ibbot_app`, which intentionally cannot
execute `apply_altdata_snapshot_correction` or write the correction ledger.
Exceptional corrections are performed out-of-band by an operator using the
`ibbot` migration/admin credential, with a non-empty actor and reason:

```sql
SELECT apply_altdata_snapshot_correction(
  <snapshot_id>, <n_rows>, '<content_hash>', '<payload>'::jsonb,
  '<reason>', '<operator>'
);
```

Run this only through the controlled admin procedure, retain the psql/audit
receipt, and verify the resulting correction row and hash-chain check. Never
put the admin URL in a service container or change the application role to
restore this capability.

## Latest verified drill

Executed 2026-08-11 from the committed offsite archive
`backups/altdata_snapshots/altdata_snapshots_20260811T234334Z.dump` into a
fresh scratch database. `postgres_fdw` in the scratch database compared the
restored table to the live database; both directions use the identity tuple
`(source, as_of_date, n_rows, content_hash)`.

```text
dump: backups/altdata_snapshots/altdata_snapshots_20260811T234334Z.dump
restored_rows: 328
live_rows: 328
restored_minus_live: 0
live_minus_restored: 0
diff_rows: 0
days_outside_expected_counts: 0
non_eleven_day_counts:
2026-07-13|9
2026-07-13 is the only day with 9 sources; missing sources: cftc_disaggregated_futures_cot, house_periodic_transaction_report_index
```
