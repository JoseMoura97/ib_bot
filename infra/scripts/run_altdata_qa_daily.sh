#!/usr/bin/env bash
# Run the same-day QA in the worker image, then commit exactly its versioned log.
set -uo pipefail

project_root=/home/servidor/Desktop/cursor-projects/ib_bot
log_relative=reports/altdata_qa_daily.jsonl
lock_path=/run/lock/ib-altdata-qa.lock

exec 9>"$lock_path"
if ! flock -n 9; then
  echo "altdata QA already running"
  exit 75
fi

cd "$project_root"
branch_name="$(git symbolic-ref --quiet --short HEAD || true)"
if [[ "$branch_name" != "main" ]]; then
  echo "refusing QA receipt commit outside main (current=$branch_name)"
  exit 2
fi

qa_status=0
docker compose exec -T worker \
  python /app/scripts/qa_altdata_snapshots.py \
  --backfill-existing \
  --log-path /app/reports/altdata_qa_daily.jsonl || qa_status=$?

if [[ -n "$(git status --porcelain -- "$log_relative")" ]]; then
  git add -- "$log_relative"
  qa_date="$(date -u +%F)"
  git commit --only -m "qa(altdata): daily receipt $qa_date" -- "$log_relative"
fi

git push origin HEAD:main

if [[ -n "$(git status --porcelain -- "$log_relative")" ]]; then
  echo "QA log remains uncommitted after persistence attempt"
  exit 3
fi

exit "$qa_status"
