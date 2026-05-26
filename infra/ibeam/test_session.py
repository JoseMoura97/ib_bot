"""
ibeam Session Smoke Test — verifies the primary ibeam container (port 5055).

Usage:
    python3 test_session.py
"""

from __future__ import annotations

import json
import sys

try:
    import httpx
    _USE_HTTPX = True
except ImportError:
    import requests  # type: ignore
    _USE_HTTPX = False

BASE_URL = "https://localhost:5055"
ENDPOINTS = [
    ("GET", "/v1/api/iserver/auth/status",  "Auth status"),
    ("GET", "/v1/api/portfolio/accounts",   "Portfolio accounts"),
    ("GET", "/v1/api/iserver/accounts",     "iServer accounts"),
]


def get(path: str) -> tuple[int, object]:
    url = BASE_URL + path
    try:
        if _USE_HTTPX:
            r = httpx.get(url, verify=False, timeout=15.0)
            return r.status_code, r.json() if r.content else {}
        else:
            r = requests.get(url, verify=False, timeout=15)
            return r.status_code, r.json() if r.content else {}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": str(exc)}


def fmt(data: object) -> str:
    try:
        return json.dumps(data, indent=2)
    except Exception:
        return str(data)


def main() -> None:
    print("=" * 60)
    print(f"  ibeam primary session test  ({BASE_URL})")
    print("=" * 60)

    not_authenticated = False

    for method, path, label in ENDPOINTS:
        code, body = get(path)
        print(f"\n[{label}]  {method} {path}")
        print(f"  HTTP {code}")
        print(fmt(body))

        if path.endswith("auth/status") and isinstance(body, dict):
            if not body.get("authenticated"):
                not_authenticated = True

    print("\n" + "=" * 60)

    if not_authenticated:
        print("  STATUS: NOT AUTHENTICATED")
        print()
        print("  ibeam is still logging in, or authentication failed.")
        print("  - Wait 30-60s after container start and retry.")
        print("  - Check logs:  docker logs -f ibeam-primary")
        print("  - Verify .env.ibeam credentials and TOTP key.")
        sys.exit(1)
    else:
        print("  STATUS: OK — session appears authenticated")
        sys.exit(0)


if __name__ == "__main__":
    main()
