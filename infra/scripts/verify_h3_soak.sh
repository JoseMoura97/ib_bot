#!/usr/bin/env bash
# H3 unattended-operation soak oracle.
#
# Requires three consecutive TIMER-FIRED green QA receipts on 2026-08-16/17/18.
#
# Why this exists (and why the phase's stored ground_truth_check is not enough):
# the frozen check counts `Finished ib-altdata-qa.service` lines in a sliding
# 4-day journal window without proving what TRIGGERED the run. On 2026-08-13 the
# 08:00 timer run FAILED (verify_altdata_chain.py: unrecognized arguments:
# --extend, the host script had drifted ahead of the baked worker image) and an
# operator re-ran the unit by hand at 08:14:24. That manual run emits an
# identical `Finished` line, so the frozen check already reaches 3 and exits 0 —
# counting an agent-triggered run as unattended proof, which is the exact
# false-green H3 was created to rule out.
#
# The first two autonomous green receipts (2026-08-14/15) proved the prior
# runner, but they predate the immutable dedicated QA image requested by the
# advisor. They cannot satisfy the revised same-digest requirement. This oracle
# therefore starts on 2026-08-16, the first scheduled run after that image pin.
# Per date it requires a durable runtime receipt, committed to origin/main,
# naming the exact digest and a start in the 08:00 WEST window; a green QA
# receipt; and no journal failure where the journal entry remains retained.
#
# Exit 0 only when all three days pass. Deliberately false until 2026-08-18.
#
# NOTE: no `set -o pipefail` here. Piping a large journal buffer into `grep -q`
# makes grep exit on first match, the writer takes SIGPIPE, and pipefail then
# reports the pipeline as failed even though the pattern matched. Match against
# here-strings instead of pipes.

set -u

REPO=${REPO:-/home/servidor/Desktop/cursor-projects/ib_bot}
UNIT=ib-altdata-qa.service
DATES=("2026-08-16" "2026-08-17" "2026-08-18")
QA_IMAGE='ib_bot-worker@sha256:a83feb6b322714b5ed07b6eaa4e3407f543be70628948f25339baa27f1369f54'

fail() { echo "H3_SOAK_RED $*"; exit 1; }

git -C "$REPO" fetch origin --quiet || fail "CANNOT_FETCH_ORIGIN"
committed=$(git -C "$REPO" show origin/main:reports/altdata_qa_daily.jsonl 2>/dev/null) \
  || fail "CANNOT_READ_COMMITTED_LOG"
runtime=$(git -C "$REPO" show origin/main:reports/altdata_qa_runtime_receipts.jsonl 2>/dev/null) \
  || fail "CANNOT_READ_RUNTIME_RECEIPTS"

for d in "${DATES[@]}"; do
  win=$(journalctl -u "$UNIT" --since "$d 08:00:00" --until "$d 08:10:00" --no-pager 2>/dev/null)

  grep -q 'Failed with result' <<<"$win" && fail "FAILED_RUN $d"

  runtime_receipt=$(grep -F "\"qa_date\":\"$d\"" <<<"$runtime" | tail -1)
  [ -n "$runtime_receipt" ]                                 || fail "NO_RUNTIME_RECEIPT $d"
  grep -Fq "\"worker_image\":\"$QA_IMAGE\"" <<<"$runtime_receipt" \
                                                            || fail "WRONG_IMAGE $d"
  grep -q '"extend_cli_verified":true' <<<"$runtime_receipt" \
                                                            || fail "EXTEND_NOT_VERIFIED $d"
  grep -q '"noninteractive_origin_verified":true' <<<"$runtime_receipt" \
                                                            || fail "GIT_NOT_VERIFIED $d"
  # 08:00 WEST is 07:00 UTC over this fixed August window. A manual 08:14
  # rerun cannot qualify, and this committed record survives journal rotation.
  grep -Eq "\"started_at_utc\":\"${d}T07:0[0-9]:[0-5][0-9]Z\"" <<<"$runtime_receipt" \
                                                            || fail "OUTSIDE_TIMER_WINDOW $d"

  receipt=$(grep -F "\"qa_date\":\"$d\"" <<<"$committed" | tail -1)
  [ -n "$receipt" ]                                   || fail "NO_COMMITTED_RECEIPT $d"
  grep -q '"status":"green"'          <<<"$receipt"   || fail "NOT_GREEN $d"
  grep -q '"eligible_for_streak":true' <<<"$receipt"  || fail "NOT_ELIGIBLE $d"

  echo "OK $d pinned-image timer-window green"
done

echo "H3_SOAK_GREEN 3/3 pinned-image (${DATES[*]})"
