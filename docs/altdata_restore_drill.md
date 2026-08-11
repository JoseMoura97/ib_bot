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

## Latest verified drill

Executed 2026-08-11 from the committed offsite archive
`backups/altdata_snapshots/altdata_snapshots_20260811T135555Z.dump` into the
fresh scratch database `ibbot_altdata_restore_h1_20260811`.  `postgres_fdw` in
the scratch database compared the restored table to the live database; both
directions use the identity tuple `(source, as_of_date, n_rows, content_hash)`.

```text
dump: backups/altdata_snapshots/altdata_snapshots_20260811T135555Z.dump
restored_rows: 328
live_rows: 328
restored_minus_live: 0
live_minus_restored: 0
diff_rows: 0
```
