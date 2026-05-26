"""
Client Portal API — session test
Run this after logging in via the browser to verify session works and persists.

Usage:
    python3 test_cpapi_session.py
"""
import time
import requests

BASE = "http://127.0.0.1:5050/v1/api"
SESSION = requests.Session()  # shares cookies

def check_status():
    r = SESSION.get(f"{BASE}/iserver/auth/status", timeout=5)
    data = r.json()
    authenticated = data.get("authenticated", False)
    competing = data.get("competing", False)
    print(f"  auth: {authenticated}  competing: {competing}  raw: {data}")
    return authenticated

def tickle():
    r = SESSION.post(f"{BASE}/tickle", timeout=5)
    return r.status_code == 200

def get_accounts():
    r = SESSION.get(f"{BASE}/portfolio/accounts", timeout=5)
    if r.status_code == 200:
        return r.json()
    return f"HTTP {r.status_code}: {r.text[:200]}"

def get_positions(account_id):
    r = SESSION.get(f"{BASE}/portfolio/{account_id}/positions/0", timeout=5)
    if r.status_code == 200:
        return r.json()
    return f"HTTP {r.status_code}: {r.text[:200]}"

if __name__ == "__main__":
    print("=== IBKR Client Portal API — session test ===\n")

    print("[1] Checking auth status...")
    authenticated = check_status()
    if not authenticated:
        print("\n  ❌ Not authenticated — log in at http://100.67.188.93:5050 first, then re-run.\n")
        exit(1)
    print("  ✓ Authenticated\n")

    print("[2] Fetching accounts...")
    accounts = get_accounts()
    print(f"  {accounts}\n")

    if isinstance(accounts, list) and accounts:
        acct_id = accounts[0].get("accountId") or accounts[0].get("id")
        print(f"[3] Fetching positions for {acct_id}...")
        positions = get_positions(acct_id)
        print(f"  {positions}\n")

    print("[4] Session persistence test (30s, tickle every 10s)...")
    for i in range(3):
        time.sleep(10)
        ok = tickle()
        authenticated = check_status()
        print(f"  t+{(i+1)*10}s — tickle: {'ok' if ok else 'FAIL'}  still auth: {authenticated}")

    print("\n=== Done ===")
    print("If authenticated stayed True throughout, session persistence works.")
    print("For production: call POST /v1/api/tickle every 55s to keep alive.")
