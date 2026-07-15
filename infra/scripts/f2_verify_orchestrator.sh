#!/usr/bin/env bash
# f2 verification orchestrator — runs detached under a transient systemd unit so it
# survives the launching session. Produces the two timestamp-bounded receipts the
# frozen acceptance of phase f2_backtest_fix_alerta needs, which the sandboxed
# worker could not (NoNewPrivileges blocked `systemctl start`):
#   Run 1 = clean weekly success run  -> criterion 1 (56/56 + plot_data updated)
#   Run 2 = controlled forced-plot-failure -> criteria 2 & 3 (non-zero propagates,
#           OnFailure fires, corrected alert writes events row WITH status=97)
# Launched by Jarvis (privileged operator) 2026-07-15. Non-money.
set -uo pipefail
LOG=/var/log/f2-verify-orchestrator.log
exec >>"$LOG" 2>&1
echo "================ f2-verify orchestrator START $(date -Is) ================"

echo "[1] clean success run START $(date -Is)"
systemctl reset-failed ib-backtests.service 2>/dev/null || true
systemctl start ib-backtests.service || true    # oneshot: blocks until done
echo "[1] success run END $(date -Is) Result=$(systemctl show ib-backtests.service -p Result --value) ExecMainStatus=$(systemctl show ib-backtests.service -p ExecMainStatus --value)"
systemctl reset-failed ib-backtests.service 2>/dev/null || true

echo "[2] controlled FAILURE run START $(date -Is)"
install -d -m 0755 /run/systemd/system/ib-backtests.service.d
printf '[Service]\nEnvironment=IB_BACKTESTS_TEST_FORCE_PLOT_FAILURE=1\n' \
  > /run/systemd/system/ib-backtests.service.d/99-f2-onfailure-test.conf
systemctl daemon-reload
systemctl start ib-backtests.service || true    # forced to fail at plot step -> OnFailure
echo "[2] failure run END $(date -Is) Result=$(systemctl show ib-backtests.service -p Result --value) ExecMainStatus=$(systemctl show ib-backtests.service -p ExecMainStatus --value)"
rm -f /run/systemd/system/ib-backtests.service.d/99-f2-onfailure-test.conf
systemctl daemon-reload
systemctl reset-failed ib-backtests.service 2>/dev/null || true

echo "================ f2-verify orchestrator DONE $(date -Is) ================"
