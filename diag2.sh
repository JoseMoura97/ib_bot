#!/bin/sh
echo "=== /app ==="
ls /app
echo "=== Framework ==="
pip list 2>/dev/null | grep -iE "ib|fastapi|django|celery|flask"
echo "=== ENV ==="
env | grep -iE "IB_|DB_|REDIS|CELERY|HOST|PORT" | sort
echo "=== Routes ==="
find /app -name "*.py" | xargs grep -l "router\|@app\." 2>/dev/null | head -10
