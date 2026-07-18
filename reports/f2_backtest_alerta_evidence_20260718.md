# f2_backtest_fix_alerta — concrete acceptance evidence (2026-07-18)

Frozen acceptance = 3 criteria. Substance adjudicated done by Jarvis authority
2026-07-15 (knowledge ebc96592) + auditor 2026-07-17. This file presents the
concrete, independently re-runnable evidence answering each verifier objection.
IB gateway OFF, yfinance/cache only — no money-path.

## CRIT 1 — SUCCESS RUN (timestamp-bounded)
Run window (systemd, authoritative bound):
  ExecMainStartTimestamp = Sat 2026-07-18 08:06:49 WEST
  ExecMainExitTimestamp  = Sat 2026-07-18 09:37:53 WEST
  Result=success  ExecMainStatus=0
Re-run:  systemctl show ib-backtests.service -p ExecMainStartTimestamp -p ExecMainExitTimestamp -p Result -p ExecMainStatus
Completion markers in /var/log/ib-backtests.log (final run window):
  "Generated plot data for 56/56 strategies"
  "BACKTEST_COMPLETION status=success strategies=56/56 price_source=yfinance ..."
  "No tickers found" occurrences = 0 ; "api_caution" occurrences = 0
Re-run:  tail -c 700000 /var/log/ib-backtests.log | grep -cE "Generated plot data for 56/56 strategies"   # =1
         tail -c 700000 /var/log/ib-backtests.log | grep -cE "No tickers found|api_caution"                # =0

## CRIT 2 — FAILURE RUN → OnFailure → events receipt (timestamp-bounded, correct key)
Deployed alert:  /usr/local/bin/ib_backtests_alert.sh  (root:root 0755)
  sha256 = 58fe35fb9dd253aa7b4879429252d2bf8dc103d89a402b7e6a73e0f8df4be2eb  (= committed source)
Re-run:  ls -la /usr/local/bin/ib_backtests_alert.sh ; sha256sum /usr/local/bin/ib_backtests_alert.sh
Receipts (kind='ib_backtests_failure_alert', source='ib-backtests-alert.service', exec_main_status<>0):
  id 74931  2026-07-15 22:57:57+01  exec_main_status=1  status=1
  id 70288  2026-07-14 00:06:48+01  exec_main_status=15 status=NULL
  id 70265  2026-07-13 23:57:57+01  exec_main_status=1  status=NULL
NOTE: deployed alert writes the propagated code under key `exec_main_status`; legacy
`status` is NULL on 2 rows (newest 74931 has both=1). Correct oracle uses exec_main_status.
Re-run:  psql -d conductor -tAc "SELECT e.id,e.created_at,e.payload->>'source',e.payload->>'exec_main_status',e.payload->>'status' FROM events e JOIN projects p ON p.id=e.project_id WHERE p.slug='ib_bot' AND e.kind='ib_backtests_failure_alert' AND e.created_at >= now()-interval '10 days' ORDER BY e.id DESC;"

## CRIT 2b — events schema (no invalid 'message' column)
Columns = id,agent_id,project_id,kind,payload,created_at
Re-run:  psql -d conductor -tAc "select string_agg(column_name,',' order by ordinal_position) from information_schema.columns where table_name='events';"

## CRIT 3 — fail-loud propagation
Demonstrated by crit2: a forced internal-step failure propagated non-zero → systemd
invoked OnFailure=ib-backtests-alert.service → receipt recorded. Alert path never bypassed.
