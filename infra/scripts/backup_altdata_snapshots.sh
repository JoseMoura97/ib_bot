#!/usr/bin/env bash
# Create a restorable, versioned offsite copy of the PIT snapshot table.
set -euo pipefail

project_root="${IB_ALTDATA_PROJECT_ROOT:-/home/servidor/Desktop/cursor-projects/ib_bot}"
archive_relative=backups/altdata_snapshots
retention_days=14
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"

cd "$project_root"

require_main() {
  local branch_name
  branch_name="$(git symbolic-ref --quiet --short HEAD || true)"
  if [[ "$branch_name" != "main" ]]; then
    echo "[altdata-backup] refusing to run outside main (current=${branch_name:-detached})" >&2
    exit 2
  fi
}

# The primary checkout belongs to timers. Lab work must use separate worktrees.
# Check before pulling, dumping, pruning, staging or publishing anything.
require_main

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

require_main

# Keep at least the most recent fourteen days of generated archives.
find "$archive_dir" -maxdepth 1 -type f -name 'altdata_snapshots_*.dump' \
  -mtime "+$retention_days" -print -delete

git add -- "$archive_relative"
git commit --only -m "backup(altdata): PIT table $timestamp" -- "$archive_relative"
require_main
git push origin refs/heads/main:refs/heads/main

echo "[altdata-backup] offsite archive pushed: $dump_file"
