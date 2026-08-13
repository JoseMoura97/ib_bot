#!/usr/bin/env bash
# Run the same-day QA in the worker image, then commit exactly its versioned log.
set -euo pipefail

project_root="${IB_ALTDATA_PROJECT_ROOT:-/home/servidor/Desktop/cursor-projects/ib_bot}"
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

# The manifest already committed on disk is the immutable baseline.  --extend
# verifies every day it already covers against live data FIRST; only if that
# passes does it append today's new day(s) and rewrite the manifest, so its top
# hash gets the same third-party Git timestamp as the day's QA evidence.  A
# retroactive rewrite of an already-committed day makes this step refuse to
# write and exit non-zero instead of silently absorbing the change into a
# freshly regenerated baseline.
docker compose exec -T worker \
  python /app/scripts/verify_altdata_chain.py \
  --extend \
  --manifest /app/reports/altdata_chain_manifest.json \
  --report /app/reports/altdata_chain_verify.json

chain_manifest_relative=reports/altdata_chain_manifest.json
chain_verify_relative=reports/altdata_chain_verify.json
if [[ -n "$(git status --porcelain -- "$log_relative" "$chain_manifest_relative" "$chain_verify_relative")" ]]; then
  git add -- "$log_relative" "$chain_manifest_relative" "$chain_verify_relative"
  qa_date="$(date -u +%F)"
  git commit --only -m "qa(altdata): daily receipt $qa_date" -- "$log_relative" "$chain_manifest_relative" "$chain_verify_relative"
fi

if git push origin HEAD:main; then
  :
else
  push_status=$?
  message="[altdata-qa] ERROR: git push origin HEAD:main failed (exit=$push_status); QA receipt is not offsite"
  echo "$message" >&2
  logger -p user.err -t ib-altdata-qa -- "$message" || true
  exit "$push_status"
fi

if [[ -n "$(git status --porcelain -- "$log_relative" "$chain_manifest_relative" "$chain_verify_relative")" ]]; then
  echo "QA receipt or hash-chain evidence remains uncommitted after persistence attempt"
  exit 3
fi

exit "$qa_status"
