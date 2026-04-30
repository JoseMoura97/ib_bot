"""
Full infrastructure test suite.
Run inside the api container: docker compose exec -T api python /tmp/run_all_tests.py
"""
import sys
import time
import traceback
import requests

RESULTS = []

def test(name, fn):
    try:
        result = fn()
        status = "PASS" if result else "WARN"
        RESULTS.append((status, name, str(result)[:200]))
        print(f"  [{status}] {name}: {str(result)[:200]}")
    except Exception as e:
        RESULTS.append(("FAIL", name, str(e)[:200]))
        print(f"  [FAIL] {name}: {e}")

# ── IB Gateway ────────────────────────────────────────────────────────────────
print("\n=== IB Gateway ===")

def t_ib_connect():
    from ib_insync import IB
    ib = IB()
    ib.connect('172.17.0.1', 4001, clientId=88, timeout=10)
    connected = ib.isConnected()
    ib.disconnect()
    return f"connected={connected}"

def t_ib_accounts():
    from ib_insync import IB
    ib = IB()
    ib.connect('172.17.0.1', 4001, clientId=87, timeout=10)
    accounts = ib.managedAccounts()
    ib.disconnect()
    return f"accounts={accounts}"

def t_ib_portfolio():
    from ib_insync import IB
    ib = IB()
    ib.connect('172.17.0.1', 4001, clientId=86, timeout=10)
    portfolio = ib.portfolio()
    cash = [v for v in ib.accountValues() if v.tag == 'CashBalance' and v.currency == 'BASE']
    ib.disconnect()
    return f"positions={len(portfolio)}, cash={cash[0].value if cash else 'N/A'}"

test("IB Gateway connect", t_ib_connect)
test("IB managed accounts", t_ib_accounts)
test("IB portfolio & cash", t_ib_portfolio)

# ── Database ──────────────────────────────────────────────────────────────────
print("\n=== Database ===")

def t_db_connect():
    import django
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
    from django.db import connection
    with connection.cursor() as c:
        c.execute("SELECT version()")
        return c.fetchone()[0][:50]

def t_db_tables():
    from django.db import connection
    with connection.cursor() as c:
        c.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
        count = c.fetchone()[0]
    return f"{count} tables"

def t_db_portfolio():
    from portfolios.models import Portfolio
    count = Portfolio.objects.count()
    return f"{count} portfolios"

test("DB connection", t_db_connect)
test("DB tables", t_db_tables)
test("DB portfolios", t_db_portfolio)

# ── Redis / Celery ────────────────────────────────────────────────────────────
print("\n=== Redis / Celery ===")

def t_redis():
    import redis
    r = redis.Redis(host='redis', port=6379)
    r.ping()
    return "Redis pong OK"

def t_celery_ping():
    from config.celery import app
    result = app.control.inspect(timeout=5).ping()
    workers = list(result.keys()) if result else []
    return f"workers={workers}"

test("Redis ping", t_redis)
test("Celery workers", t_celery_ping)

# ── API endpoints ─────────────────────────────────────────────────────────────
print("\n=== API Endpoints ===")

BASE = "http://localhost:8000"

def t_api_health():
    r = requests.get(f"{BASE}/api/health/", timeout=5)
    return f"status={r.status_code} body={r.text[:80]}"

def t_api_portfolios():
    r = requests.get(f"{BASE}/api/portfolios/", timeout=5)
    return f"status={r.status_code}"

def t_api_prices():
    r = requests.get(f"{BASE}/api/prices/?symbol=AAPL", timeout=10)
    return f"status={r.status_code}"

test("GET /api/health/", t_api_health)
test("GET /api/portfolios/", t_api_portfolios)
test("GET /api/prices/", t_api_prices)

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "="*50)
passed = sum(1 for s,_,_ in RESULTS if s=="PASS")
warned = sum(1 for s,_,_ in RESULTS if s=="WARN")
failed = sum(1 for s,_,_ in RESULTS if s=="FAIL")
print(f"RESULTS: {passed} passed, {warned} warned, {failed} failed / {len(RESULTS)} total")
print("="*50)
if failed:
    print("\nFailed tests:")
    for s,n,m in RESULTS:
        if s=="FAIL":
            print(f"  - {n}: {m}")
