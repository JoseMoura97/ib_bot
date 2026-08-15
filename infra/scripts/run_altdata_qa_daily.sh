#!/usr/bin/env bash
# Run the same-day QA in the worker image, then commit exactly its versioned log.
set -euo pipefail

project_root="${IB_ALTDATA_PROJECT_ROOT:-/home/servidor/Desktop/cursor-projects/ib_bot}"
log_relative=reports/altdata_qa_daily.jsonl
runtime_receipt_relative=reports/altdata_qa_runtime_receipts.jsonl
qa_service=altdata_qa
lock_path=/run/lock/ib-altdata-qa.lock

exec 9>"$lock_path"
if ! flock -n 9; then
  echo "altdata QA already running"
  exit 75
fi

cd "$project_root"
run_started_at_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
branch_name="$(git symbolic-ref --quiet --short HEAD || true)"
if [[ "$branch_name" != "main" ]]; then
  echo "refusing QA receipt commit outside main (current=$branch_name)"
  exit 2
fi

# Fail before touching the daily receipt if the dedicated QA service is no
# longer the exact image that exposes the extend-capable chain verifier.
qa_image="$(docker compose config --images | grep -Fx 'ib_bot-worker@sha256:a83feb6b322714b5ed07b6eaa4e3407f543be70628948f25339baa27f1369f54' || true)"
if [[ -z "$qa_image" ]]; then
  echo "QA_IMAGE_GATE: dedicated pinned altdata_qa image is absent from resolved Compose config" >&2
  exit 4
fi
qa_digest="${qa_image##*@}"
actual_qa_digest="$(docker image inspect "$qa_image" --format '{{.Id}}' 2>/dev/null || true)"
if [[ "$actual_qa_digest" != "$qa_digest" ]]; then
  echo "QA_IMAGE_GATE: expected $qa_digest, found ${actual_qa_digest:-missing}" >&2
  exit 4
fi
extend_help="$(docker compose run --rm --no-deps --entrypoint python "$qa_service" /app/scripts/verify_altdata_chain.py --help 2>&1)"
if ! grep -Fq -- '--extend' <<<"$extend_help"; then
  echo "QA_IMAGE_GATE: pinned image does not expose verify_altdata_chain.py --extend" >&2
  exit 4
fi
# Never permit a timer run to block on an interactive Git credential prompt.
if ! GIT_TERMINAL_PROMPT=0 git ls-remote --exit-code origin refs/heads/main >/dev/null 2>&1; then
  echo "QA_GIT_GATE: non-interactive origin/main authentication failed" >&2
  exit 4
fi

qa_status=0
docker compose run --rm --no-deps "$qa_service" \
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
docker compose run --rm --no-deps "$qa_service" \
  python /app/scripts/verify_altdata_chain.py \
  --extend \
  --manifest /app/reports/altdata_chain_manifest.json \
  --report /app/reports/altdata_chain_verify.json

chain_manifest_relative=reports/altdata_chain_manifest.json
chain_verify_relative=reports/altdata_chain_verify.json
qa_date="$(date -u +%F)"
printf '{"qa_date":"%s","worker_image":"%s","worker_image_digest":"%s","extend_cli_verified":true,"noninteractive_origin_verified":true,"started_at_utc":"%s","preflight_at_utc":"%s"}\n' \
  "$qa_date" "$qa_image" "$qa_digest" "$run_started_at_utc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$runtime_receipt_relative"
if [[ -n "$(git status --porcelain -- "$log_relative" "$chain_manifest_relative" "$chain_verify_relative" "$runtime_receipt_relative")" ]]; then
  git add -- "$log_relative" "$chain_manifest_relative" "$chain_verify_relative" "$runtime_receipt_relative"
  git commit --only -m "qa(altdata): daily receipt $qa_date" -- "$log_relative" "$chain_manifest_relative" "$chain_verify_relative" "$runtime_receipt_relative"
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

if [[ -n "$(git status --porcelain -- "$log_relative" "$chain_manifest_relative" "$chain_verify_relative" "$runtime_receipt_relative")" ]]; then
  echo "QA receipt or hash-chain evidence remains uncommitted after persistence attempt"
  exit 3
fi

exit "$qa_status"
