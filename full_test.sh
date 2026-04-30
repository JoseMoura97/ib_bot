#!/bin/bash
BASE="http://localhost:8000"
PASS=0
FAIL=0
WARN=0

run() {
    local name="$1"
    local url="$2"
    local expected="$3"
    local result
    result=$(curl -s -o /tmp/resp.json -w "%{http_code}" --max-time 15 "$url")
    body=$(cat /tmp/resp.json 2>/dev/null)
    if [ "$result" = "$expected" ]; then
        echo "  [PASS] $name (HTTP $result): ${body:0:120}"
        PASS=$((PASS+1))
    else
        echo "  [FAIL] $name (HTTP $result, expected $expected): ${body:0:120}"
        FAIL=$((FAIL+1))
    fi
}

run_any() {
    local name="$1"
    local url="$2"
    local result
    result=$(curl -s -o /tmp/resp.json -w "%{http_code}" --max-time 15 "$url")
    body=$(cat /tmp/resp.json 2>/dev/null)
    if [ "$result" -ge 200 ] && [ "$result" -lt 500 ]; then
        echo "  [PASS] $name (HTTP $result): ${body:0:120}"
        PASS=$((PASS+1))
    else
        echo "  [FAIL] $name (HTTP $result): ${body:0:120}"
        FAIL=$((FAIL+1))
    fi
}

echo ""
echo "=== Health ==="
run "GET /health" "$BASE/health" "200"

echo ""
echo "=== IB Gateway ==="
run_any "GET /ib/status" "$BASE/ib/status"
run_any "GET /ib/accounts" "$BASE/ib/accounts"

echo ""
echo "=== Portfolios ==="
run_any "GET /portfolios" "$BASE/portfolios"

echo ""
echo "=== Strategies ==="
run_any "GET /strategies" "$BASE/strategies"

echo ""
echo "=== Dashboard ==="
run_any "GET /dashboard" "$BASE/dashboard"

echo ""
echo "=== Allocations ==="
run_any "GET /allocations" "$BASE/allocations"

echo ""
echo "=== Runs ==="
run_any "GET /runs" "$BASE/runs"

echo ""
echo "=== Paper ==="
run_any "GET /paper" "$BASE/paper"

echo ""
echo "=== Metrics ==="
run_any "GET /metrics" "$BASE/metrics"

echo ""
echo "=== Live ==="
run_any "GET /live" "$BASE/live"

echo ""
echo "=================================================="
echo "RESULTS: $PASS passed, $FAIL failed"
echo "=================================================="
