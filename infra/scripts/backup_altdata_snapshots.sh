#!/usr/bin/env bash
# Create a restorable, versioned offsite copy of the PIT snapshot table.
set -euo pipefail

project_root=/home/servidor/Desktop/cursor-projects/ib_bot
archive_relative=backups/altdata_snapshots
retention_days=14
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"

cd "$project_root"

# Never add an unrelated local change to an automated backup commit.
if [[ -n "$(git status --porcelain)" ]]; then
  echo "[altdata-backup] refusing to run: working tree is dirty" >&2
  exit 2
fi

git pull --ff-only origin main

archive_dir="$project_root/$archive_relative"
mkdir -p "$archive_dir"
dump_file="$archive_dir/altdata_snapshots_${timestamp}.dump"
temporary_dump="${dump_file}.partial"
trap 'rm -f "$temporary_dump"' EXIT

# Custom format includes this table's schema, indexes, constraints and data.
docker compose exec -T db pg_dump -U ibbot -d ibbot -Fc \
  -t public.altdata_snapshots > "$temporary_dump"

if [[ ! -s "$temporary_dump" ]]; then
  echo "[altdata-backup] ERROR: pg_dump produced an empty archive" >&2
  exit 3
fi
if ! pg_restore --list "$temporary_dump" | grep -q 'TABLE DATA public altdata_snapshots'; then
  echo "[altdata-backup] ERROR: archive does not contain altdata_snapshots data" >&2
  exit 4
fi
mv "$temporary_dump" "$dump_file"

# Keep at least the most recent fourteen days of generated archives.
find "$archive_dir" -maxdepth 1 -type f -name 'altdata_snapshots_*.dump' \
  -mtime "+$retention_days" -print -delete

git add -- "$archive_relative"
git commit -m "backup(altdata): PIT table $timestamp"
git push origin HEAD:main

echo "[altdata-backup] offsite archive pushed: $dump_file"
