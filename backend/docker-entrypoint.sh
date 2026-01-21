#!/usr/bin/env sh
set -eu

wait_for_postgres() {
  python - <<'PY'
import os
import time
from sqlalchemy import create_engine, text

url = os.getenv("DATABASE_URL") or ""
if not url:
    raise SystemExit("DATABASE_URL is not set")

deadline = time.time() + float(os.getenv("WAIT_FOR_DB_SECONDS") or "60")
last_err = None
while time.time() < deadline:
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("DB ready")
        raise SystemExit(0)
    except Exception as e:
        last_err = e
        time.sleep(1.0)

raise SystemExit(f"DB not ready after timeout: {last_err}")
PY
}

wait_for_redis() {
  python - <<'PY'
import os
import socket
import time
from urllib.parse import urlparse

url = os.getenv("REDIS_URL") or ""
if not url:
    raise SystemExit("REDIS_URL is not set")

u = urlparse(url)
host = u.hostname or "redis"
port = int(u.port or 6379)

deadline = time.time() + float(os.getenv("WAIT_FOR_REDIS_SECONDS") or "60")
last_err = None
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            print("Redis ready")
            raise SystemExit(0)
    except Exception as e:
        last_err = e
        time.sleep(1.0)

raise SystemExit(f"Redis not ready after timeout: {last_err}")
PY
}

wait_for_postgres
wait_for_redis

echo "Running migrations..."
alembic -c backend/alembic.ini upgrade head

echo "Starting: $*"
exec "$@"

