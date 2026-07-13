#!/usr/bin/env bash
set -euo pipefail

refresh_since=""
if [[ ${1:-} == "--require-refresh-since" && -n ${2:-} ]]; then
  refresh_since=$2
elif [[ $# -ne 0 ]]; then
  echo "usage: $0 [--require-refresh-since ISO-8601]" >&2
  exit 2
fi

failures=0
check_equal() {
  local label=$1 expected=$2 actual=$3
  if [[ $actual == "$expected" ]]; then
    printf 'PASS %-28s %s\n' "$label" "$actual"
  else
    printf 'FAIL %-28s expected=%s actual=%s\n' "$label" "$expected" "$actual"
    failures=$((failures + 1))
  fi
}

mapfile -t system_states < <(systemctl is-active \
  ibgateway.service xvfb-ibgw.service ib-socat.service ibgw-watchdog.service || true)
check_equal "system-units-count" "4" "${#system_states[@]}"
for index in "${!system_states[@]}"; do
  check_equal "system-unit-$((index + 1))" "inactive" "${system_states[$index]}"
done

user_vnc_state=$(XDG_RUNTIME_DIR=/run/user/1000 systemctl --user is-active \
  ibgw-vnc-loopback.service || true)
check_equal "user-vnc" "inactive" "$user_vnc_state"

ibeam_count=$(docker ps --format '{{.Names}}' | grep -c ibeam || true)
v2_count=$(docker ps --format '{{.Names}}' | grep -c 'ib_bot-v2' || true)
target_port_count=$(ss -tlnp | grep -cE ':4001 |:5900 |:8092 |:3002 ' || true)
check_equal "ibeam-containers" "0" "$ibeam_count"
check_equal "v2-containers" "0" "$v2_count"
check_equal "target-listeners" "0" "$target_port_count"

mapfile -t timer_states < <(systemctl is-active ib-backtests.timer lifeos-ib-refresh.timer || true)
check_equal "timers-count" "2" "${#timer_states[@]}"
for index in "${!timer_states[@]}"; do
  check_equal "timer-$((index + 1))" "active" "${timer_states[$index]}"
done

v1_container_count=$(docker ps --format '{{.Names}}' | grep -cE '^ib_bot-(api|db|redis|nginx|web|worker|beat)-1$' || true)
check_equal "v1-containers" "7" "$v1_container_count"

root_headers=$(mktemp)
trap 'rm -f "$root_headers"' EXIT
root_code=$(curl -sS -D "$root_headers" -o /dev/null -w '%{http_code}' http://127.0.0.1:3001/ || true)
follow_code=$(curl -LsS -o /dev/null -w '%{http_code}' http://127.0.0.1:3001/ || true)
if [[ $root_code == "200" ]]; then
  printf 'PASS %-28s %s\n' "frontend-root" "$root_code"
elif [[ $root_code == "307" ]] && grep -qi '^location: /dashboard' "$root_headers"; then
  printf 'EXCL %-28s 307->/dashboard (pre-existing Next.js redirect)\n' "frontend-root-raw"
else
  printf 'FAIL %-28s expected=200-or-307-to-dashboard actual=%s\n' "frontend-root" "$root_code"
  failures=$((failures + 1))
fi
check_equal "frontend-follow" "200" "$follow_code"

if [[ -n $refresh_since ]]; then
  refresh_log=$(journalctl -u lifeos-ib-refresh.service --since "$refresh_since" --no-pager)
  pushed_count=$(grep -cF 'pushed: {"status":"ok"' <<<"$refresh_log" || true)
  finished_count=$(grep -cF 'Finished lifeos-ib-refresh.service' <<<"$refresh_log" || true)
  if (( pushed_count >= 1 )); then
    printf 'PASS %-28s %s\n' "post-dormancy-pushed" "$pushed_count"
  else
    printf 'FAIL %-28s expected=>=1 actual=%s\n' "post-dormancy-pushed" "$pushed_count"
    failures=$((failures + 1))
  fi
  if (( finished_count >= 1 )); then
    printf 'PASS %-28s %s\n' "post-dormancy-finished" "$finished_count"
  else
    printf 'FAIL %-28s expected=>=1 actual=%s\n' "post-dormancy-finished" "$finished_count"
    failures=$((failures + 1))
  fi
fi

if (( failures > 0 )); then
  printf 'RESULT FAIL failures=%d\n' "$failures"
  exit 1
fi
printf 'RESULT PASS failures=0\n'
