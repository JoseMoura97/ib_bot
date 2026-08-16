#!/usr/bin/env bash
# H3 soak FAIL-FAST detector (companion to verify_h3_soak.sh).
#
# verify_h3_soak.sh answers "is the soak green yet?" and stays red both while the
# soak is merely INCOMPLETE and when it is BROKEN. A durable guard armed on it
# therefore cannot tell "day 2 has not happened yet" from "day 2 fired and
# failed" — it just keeps polling until its deadline. That is precisely how the
# 2026-08-13 producer defect (verify_altdata_chain.py: unrecognized arguments:
# --extend, host script drifted ahead of the baked worker image) burned days
# before anyone looked.
#
# The 2026-08-13 advisor ruling required the opposite: wake IMMEDIATELY on any
# 08:00 failure or digest/author divergence, and do not wait for day three to
# discover the producer is still invalid. This script is that gate.
#
# Semantics are INVERTED relative to verify_h3_soak.sh, because a durable
# cmd_exit0 job wakes on exit 0:
#   exit 0  => the soak is BROKEN for a day that has already had its chance.
#              Wake the owner now; the pinned 08-16/17/18 window cannot be
#              satisfied any more without operator action.
#   exit 1  => nothing broken yet (day still pending, or its receipt conforms).
#
# Only POSITIVE evidence of failure wakes. Transient conditions that merely hide
# evidence (origin unreachable, receipts file unreadable) exit 1 — the soak
# guard's own producer_alive_cmd covers timer death, and a false wake here would
# train the owner to ignore this alarm.
#
# NOTE: no `set -o pipefail`, and no piping into `grep -q` — grep exits on first
# match, the writer takes SIGPIPE and pipefail reports a matched pattern as a
# failed pipeline. Match against here-strings, same as verify_h3_soak.sh.

set -u

REPO=${REPO:-/home/servidor/Desktop/cursor-projects/ib_bot}
UNIT=ib-altdata-qa.service
DATES=("2026-08-17" "2026-08-18")
QA_IMAGE='ib_bot-worker@sha256:a83feb6b322714b5ed07b6eaa4e3407f543be70628948f25339baa27f1369f54'

# The timer fires at 08:00 WEST (07:00 UTC). The runner then commits and pushes
# its receipts. Give the push 30 real minutes before "no receipt" counts as a
# failure, so a slow push is never mistaken for a broken producer.
GRACE_UTC="07:30:00"

wake() { echo "H3_FAILFAST_TRIP $*"; exit 0; }

now_epoch=$(date -u +%s)

# A run that systemd itself recorded as failed is conclusive and needs no grace
# period — report it the moment it lands.
for d in "${DATES[@]}"; do
  win=$(journalctl -u "$UNIT" --since "$d 08:00:00" --until "$d 08:10:00" --no-pager 2>/dev/null)
  grep -q 'Failed with result' <<<"$win" && wake "FAILED_RUN $d"
done

git -C "$REPO" fetch origin --quiet 2>/dev/null || exit 1
runtime=$(git -C "$REPO" show origin/main:reports/altdata_qa_runtime_receipts.jsonl 2>/dev/null) || exit 1
committed=$(git -C "$REPO" show origin/main:reports/altdata_qa_daily.jsonl 2>/dev/null) || exit 1

for d in "${DATES[@]}"; do
  deadline_epoch=$(date -u -d "${d}T${GRACE_UTC}Z" +%s 2>/dev/null) || exit 1
  # Day has not had its chance yet: silence is expected, not a defect.
  [ "$now_epoch" -lt "$deadline_epoch" ] && continue

  runtime_receipt=$(grep -F "\"qa_date\":\"$d\"" <<<"$runtime" | tail -1)
  [ -n "$runtime_receipt" ] || wake "NO_RUNTIME_RECEIPT $d"

  grep -Fq "\"worker_image\":\"$QA_IMAGE\"" <<<"$runtime_receipt" \
    || wake "WRONG_IMAGE $d"
  grep -q '"extend_cli_verified":true' <<<"$runtime_receipt" \
    || wake "EXTEND_NOT_VERIFIED $d"
  grep -q '"noninteractive_origin_verified":true' <<<"$runtime_receipt" \
    || wake "GIT_NOT_VERIFIED $d"
  grep -Eq "\"started_at_utc\":\"${d}T07:0[0-9]:[0-5][0-9]Z\"" <<<"$runtime_receipt" \
    || wake "OUTSIDE_TIMER_WINDOW $d"

  receipt=$(grep -F "\"qa_date\":\"$d\"" <<<"$committed" | tail -1)
  [ -n "$receipt" ]                                  || wake "NO_COMMITTED_RECEIPT $d"
  grep -q '"status":"green"'           <<<"$receipt" || wake "NOT_GREEN $d"
  grep -q '"eligible_for_streak":true' <<<"$receipt" || wake "NOT_ELIGIBLE $d"
done

echo "H3_FAILFAST_CLEAR nothing broken (as of $(date -u +%Y-%m-%dT%H:%M:%SZ))"
exit 1
