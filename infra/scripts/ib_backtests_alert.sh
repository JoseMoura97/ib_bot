#!/usr/bin/env bash
# OnFailure handler for ib-backtests.service.
#
# When the weekly backtest service fails (any internal step propagates a
# non-zero exit -> systemd ExecMainStatus != 0 -> unit enters `failed`), this
# script arms a durable Conductor job that WAKES the ib_bot Domain Manager so it
# can diagnose and re-run the backtest autonomously — no human in the loop.
#
# Binding note from Jose (Finding:5, 2026-07-13): "corrigir a falha, adicionar
# alerta automatico da falha como wake do manager para resolver".
#
# Deployed to /usr/local/bin/ib_backtests_alert.sh (stable path, independent of
# the git checkout). Repo copy kept here for reproducibility.
set -uo pipefail

TS="$(date -Is)"
STATUS="$(systemctl show ib-backtests.service -p ExecMainStatus --value 2>/dev/null || echo '?')"
RESULT="$(systemctl show ib-backtests.service -p Result --value 2>/dev/null || echo '?')"
# Last lines of the run log (strip NULs; cap size so the resume message stays sane).
LOGTAIL="$(tail -n 20 /var/log/ib-backtests.log 2>/dev/null | tr -d '\000' | tail -c 1200)"

conductor jobs add \
  --owner ib_bot \
  --mode resume \
  --wake-kind cmd_exit0 \
  --wake-spec '{"cmd":"true"}' \
  --deadline-min 1440 \
  --created-by ib-backtests-onfailure \
  --title "ib-backtests.service FAILED (ExecMainStatus=${STATUS}, Result=${RESULT}) @ ${TS}" \
  --resume-message "AUTO-ALERT: the weekly ib-backtests.service FAILED at ${TS} (ExecMainStatus=${STATUS}, Result=${RESULT}). Investigate /var/log/ib-backtests.log — delimit the run by its start timestamp; journalctl only has Start/Finished lines. Fix the failing internal step, then re-run 'sudo systemctl start ib-backtests.service' until ExecMainStatus=0 with 56/56 strategies OK and the dashboard/plot_data step complete (zero 'No tickers found', zero 'api_caution' refusal). Recent log tail: ${LOGTAIL}"
rc=$?

# Best-effort breadcrumb into the conductor events table for the audit oracle.
psql conductor -v ts="${TS}" -v st="${STATUS}" -v rc="${rc}" <<'SQL' 2>/dev/null || true
INSERT INTO events (project_id, kind, payload)
SELECT id, 'ib_backtests_failure_alert',
       jsonb_build_object('ts', :'ts', 'status', (:'st')::integer,
                          'exec_main_status', :'st', 'job_add_rc', :'rc',
                          'source', 'ib-backtests-alert.service')
FROM projects WHERE slug = 'ib_bot' LIMIT 1;
SQL

exit 0
