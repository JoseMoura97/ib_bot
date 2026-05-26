"""
ibeam Keepalive — background script that tickles all running ibeam containers
every 55 seconds to prevent IB session expiry.

Usage:
    python3 keepalive.py

Containers are discovered dynamically via Docker SDK (name prefix: ibeam-).
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta

import docker
import requests  # fallback if httpx not installed

try:
    import httpx
    _USE_HTTPX = True
except ImportError:
    _USE_HTTPX = False

TICKLE_INTERVAL = 55        # seconds between tickle rounds
IBEAM_INTERNAL_PORT = 5000  # container-internal port
FAIL_THRESHOLD = 3          # consecutive failures before logging SESSION DEAD

ART = timezone(timedelta(hours=-3))  # Buenos Aires Time (UTC-3)


def art_now() -> str:
    return datetime.now(ART).strftime("%Y-%m-%d %H:%M:%S ART")


def get_ibeam_containers(client: docker.DockerClient) -> list[tuple[str, int]]:
    """Return list of (account_id, host_port) for all running ibeam-* containers."""
    result = []
    try:
        containers = client.containers.list(
            filters={"name": "ibeam-", "status": "running"}
        )
        for c in containers:
            name: str = c.name
            if not name.startswith("ibeam-"):
                continue
            account_id = name[len("ibeam-"):]
            bindings = c.ports.get(f"{IBEAM_INTERNAL_PORT}/tcp")
            if not bindings:
                continue
            host_port = int(bindings[0]["HostPort"])
            result.append((account_id, host_port))
    except Exception as exc:  # noqa: BLE001
        print(f"[{art_now()}] ERROR listing containers: {exc}")
    return result


def tickle(port: int) -> tuple[bool, int]:
    """POST /v1/api/tickle to the ibeam container. Returns (success, http_code)."""
    url = f"https://localhost:{port}/v1/api/tickle"
    try:
        if _USE_HTTPX:
            resp = httpx.post(url, verify=False, timeout=10.0)
        else:
            resp = requests.post(url, verify=False, timeout=10)
        return resp.status_code < 400, resp.status_code
    except Exception:  # noqa: BLE001
        return False, 0


def run_keepalive() -> None:
    client = docker.from_env()
    consecutive_failures: dict[str, int] = defaultdict(int)
    dead_accounts: set[str] = set()

    print(f"[{art_now()}] ibeam keepalive started (interval={TICKLE_INTERVAL}s)")

    while True:
        containers = get_ibeam_containers(client)

        if not containers:
            print(f"[{art_now()}] No running ibeam containers found.")
        else:
            for account_id, port in containers:
                ok, code = tickle(port)
                status_str = "ok" if ok else f"FAIL (http {code})"
                print(f"[{art_now()}] {account_id} tickle: {status_str}")

                if ok:
                    consecutive_failures[account_id] = 0
                    dead_accounts.discard(account_id)
                else:
                    consecutive_failures[account_id] += 1
                    fails = consecutive_failures[account_id]
                    if fails >= FAIL_THRESHOLD and account_id not in dead_accounts:
                        print(
                            f"[{art_now()}] SESSION DEAD: {account_id} "
                            f"({fails} consecutive failures — ibeam restart_policy will recover)"
                        )
                        dead_accounts.add(account_id)

        time.sleep(TICKLE_INTERVAL)


if __name__ == "__main__":
    run_keepalive()
