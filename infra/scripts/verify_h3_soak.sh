#!/usr/bin/env bash
# H3 unattended-operation soak oracle.
#
# Requires three consecutive TIMER-FIRED green QA receipts on 2026-08-14/15/16.
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
# This oracle instead pins the three post-fix dates and, per date, requires:
#   1. a start inside the 08:00 timer window (manual re-runs land outside it),
#   2. a Finished line in that same window,
#   3. no failure in that window,
#   4. a committed green receipt on origin/main for that qa_date,
#   5. eligible_for_streak=true on that receipt.
#
# Exit 0 only when all three days pass. Deliberately false until 2026-08-16.
#
# NOTE: no `set -o pipefail` here. Piping a large journal buffer into `grep -q`
# makes grep exit on first match, the writer takes SIGPIPE, and pipefail then
# reports the pipeline as failed even though the pattern matched. Match against
# here-strings instead of pipes.

set -u

REPO=${REPO:-/home/servidor/Desktop/cursor-projects/ib_bot}
UNIT=ib-altdata-qa.service
DATES=("2026-08-14" "2026-08-15" "2026-08-16")

fail() { echo "H3_SOAK_RED $*"; exit 1; }

git -C "$REPO" fetch origin --quiet 2>/dev/null || true
committed=$(git -C "$REPO" show origin/main:reports/altdata_qa_daily.jsonl 2>/dev/null) \
  || fail "CANNOT_READ_COMMITTED_LOG"

for d in "${DATES[@]}"; do
  win=$(journalctl -u "$UNIT" --since "$d 08:00:00" --until "$d 08:10:00" --no-pager 2>/dev/null)

  grep -q "Starting $UNIT"  <<<"$win" || fail "NO_TIMER_START $d"
  grep -q "Finished $UNIT"  <<<"$win" || fail "NO_FINISH $d"
  grep -q 'Failed with result' <<<"$win" && fail "FAILED_RUN $d"

  receipt=$(grep -F "\"qa_date\":\"$d\"" <<<"$committed" | tail -1)
  [ -n "$receipt" ]                                   || fail "NO_COMMITTED_RECEIPT $d"
  grep -q '"status":"green"'          <<<"$receipt"   || fail "NOT_GREEN $d"
  grep -q '"eligible_for_streak":true' <<<"$receipt"  || fail "NOT_ELIGIBLE $d"

  echo "OK $d timer-fired green"
done

echo "H3_SOAK_GREEN 3/3 (${DATES[*]})"
