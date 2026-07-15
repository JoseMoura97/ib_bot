#!/usr/bin/env bash
# Repair the stale phase-f2 systemd override, rerun the weekly backtest, and
# write a durable success receipt only after every production oracle passes.
set -Eeuo pipefail

PROJECT_ROOT=/home/servidor/Desktop/cursor-projects/ib_bot
UNIT=ib-backtests.service
SERVICE_DROPIN_DIR=/etc/systemd/system/ib-backtests.service.d
RUNTIME_DROPIN_DIR=/run/systemd/system/ib-backtests.service.d
STALE_DROPIN="$SERVICE_DROPIN_DIR/30-phasef2-worktree.conf"
CONTAINMENT_SOURCE="$PROJECT_ROOT/infra/systemd/ib-backtests.service.d/15-preflight-containment.conf"
CONTAINMENT_TARGET="$SERVICE_DROPIN_DIR/15-preflight-containment.conf"
BACKTEST_LOG=/var/log/ib-backtests.log
SEGMENT_LOG=/var/tmp/ib-backtests-remediation-segment.log
META=/var/tmp/ib-backtests-remediation.meta
DONE=/var/tmp/ib-backtests-remediation.done
FAILED=/var/tmp/ib-backtests-remediation.failed

if [[ ${EUID} -ne 0 ]]; then
  echo "This remediation must run as root." >&2
  exit 77
fi

rm -f "$DONE" "$FAILED"

on_error() {
  local rc=$?
  {
    echo "status=failed"
    echo "exit_code=$rc"
    echo "failed_at=$(date -Is)"
    systemctl show "$UNIT" -p Result -p ExecMainStatus -p ExecMainStartTimestamp -p ExecMainExitTimestamp || true
  } >"$FAILED"
  exit "$rc"
}
trap on_error ERR

install -D -m 0644 "$CONTAINMENT_SOURCE" "$CONTAINMENT_TARGET"

if [[ -f "$STALE_DROPIN" ]]; then
  mv "$STALE_DROPIN" "/var/tmp/ib-backtests.30-phasef2-worktree.conf.stale-$(date +%Y%m%dT%H%M%S%z)"
fi

# A prior controlled-failure oracle must never leak into a production rerun.
rm -f "$RUNTIME_DROPIN_DIR/99-f2-onfailure-test.conf"
systemctl daemon-reload
systemctl reset-failed "$UNIT" || true

effective_exec=$(systemctl show "$UNIT" -p ExecStart --value)
if [[ "$effective_exec" == *"/.worktrees/"* ]]; then
  echo "Refusing rerun: effective ExecStart still targets a worktree: $effective_exec" >&2
  exit 78
fi

start_ts=$(date -Is)
start_epoch=$(date +%s)
start_offset=$(stat -c %s "$BACKTEST_LOG")
{
  echo "status=running"
  echo "start_ts=$start_ts"
  echo "start_epoch=$start_epoch"
  echo "start_offset=$start_offset"
  echo "git_commit=$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
  echo "effective_exec=$effective_exec"
} >"$META"

systemctl start "$UNIT"

exec_status=$(systemctl show "$UNIT" -p ExecMainStatus --value)
result=$(systemctl show "$UNIT" -p Result --value)
[[ "$exec_status" == "0" ]]
[[ "$result" == "success" ]]

tail -c "+$((start_offset + 1))" "$BACKTEST_LOG" >"$SEGMENT_LOG"

grep -Fq "Summary: 56 succeeded, 0 failed, 0 skipped" "$SEGMENT_LOG"
grep -Fq "Generated plot data for 56/56 strategies" "$SEGMENT_LOG"
grep -Fq "BACKTEST_COMPLETION status=success strategies=56/56" "$SEGMENT_LOG"
if grep -Fq "No tickers found" "$SEGMENT_LOG"; then
  echo "Acceptance failure: bounded rerun contains 'No tickers found'." >&2
  exit 79
fi
if grep -Eiq "api_caution: refusing|api_caution[^[:cntrl:]]*refusal" "$SEGMENT_LOG"; then
  echo "Acceptance failure: bounded rerun contains an api_caution refusal." >&2
  exit 80
fi

artifact="$PROJECT_ROOT/.cache/plot_data.json"
[[ -s "$artifact" ]]
artifact_mtime=$(stat -c %Y "$artifact")
(( artifact_mtime >= start_epoch ))
PLOT_DATA_ARTIFACT="$artifact" "$PROJECT_ROOT/.venv/bin/python" - <<'PY'
import json
import os
from pathlib import Path

artifact = Path(os.environ["PLOT_DATA_ARTIFACT"])
payload = json.loads(artifact.read_text(encoding="utf-8"))
count = len(payload.get("strategies", {}))
if count != 56:
    raise SystemExit(f"plot_data strategy count is {count}, expected 56")
PY

end_ts=$(date -Is)
receipt_tmp="${DONE}.tmp.$$"
{
  echo "0"
  echo "status=success"
  echo "start_ts=$start_ts"
  echo "end_ts=$end_ts"
  echo "exec_main_status=$exec_status"
  echo "result=$result"
  echo "strategies=56/56"
  echo "plot_data_artifact=$artifact"
  echo "segment_log=$SEGMENT_LOG"
} >"$receipt_tmp"
mv "$receipt_tmp" "$DONE"
rm -f "$FAILED"
trap - ERR
