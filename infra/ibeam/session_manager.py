"""
ibeam Session Manager — FastAPI service on port 5056
Manages multiple ibeam Docker containers dynamically, one per IB account.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import docker
import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
IBEAM_IMAGE = "voyz/ibeam:latest"
BASE_PORT = 5060          # dynamic containers start here
IBEAM_INTERNAL_PORT = 5000

app = FastAPI(title="ibeam Session Manager", version="1.0.0")
docker_client = docker.from_env()

# {account_id: {port, container_name, status, last_tickle}}
sessions: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _next_port() -> int:
    """Return the lowest port >= BASE_PORT not already in use by a session."""
    used = {s["port"] for s in sessions.values()}
    port = BASE_PORT
    while port in used:
        port += 1
    return port


def _container_name(account_id: str) -> str:
    safe = account_id.replace(".", "-").replace("@", "-").lower()
    return f"ibeam-{safe}"


def _ibeam_base_url(port: int) -> str:
    return f"https://localhost:{port}"


async def _get_auth_status(port: int) -> dict[str, Any]:
    url = f"{_ibeam_base_url(port)}/v1/api/iserver/auth/status"
    async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class CreateSessionRequest(BaseModel):
    account: str
    password: str
    totp_key: str


class SessionInfo(BaseModel):
    session_id: str
    port: int
    container_name: str
    status: str
    last_tickle: float | None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/sessions", status_code=201)
async def create_session(body: CreateSessionRequest) -> dict[str, Any]:
    """Spin up a new ibeam container for the given account credentials."""
    account_id = body.account

    if account_id in sessions:
        raise HTTPException(
            status_code=409,
            detail=f"Session for account '{account_id}' already exists. "
                   "DELETE it first to recreate.",
        )

    port = _next_port()
    name = _container_name(account_id)

    env = {
        "IBEAM_ACCOUNT": body.account,
        "IBEAM_PASSWORD": body.password,
        # TOTP via PYOTP — matches the working .env.ibeam config
        "IBEAM_TWO_FA_HANDLER": "PYOTP",
        "IBEAM_PYOTP_SECRET": body.totp_key,
        # IBKR login page selectors: "Select Second Factor Device" dropdown → silver response field
        "IBEAM_TWO_FA_SELECT_EL_ID": "CLASS_NAME@@xyz-multipleselect",
        "IBEAM_TWO_FA_SELECT_TARGET": "Mobile Authenticator App",
        "IBEAM_TWO_FA_EL_ID": "ID@@xyz-field-silver-response",
        "IBEAM_TWO_FA_INPUT_EL_ID": "ID@@xyz-field-silver-response",
        "IBEAM_INPUTS_DIR": "/srv/inputs",
        "IBEAM_OUTPUTS_DIR": "/srv/outputs",
        "IBEAM_LOG_LEVEL": "INFO",
        "IBEAM_PAGE_LOAD_TIMEOUT": "60",
        "IBEAM_OAUTH_TIMEOUT": "60",
        "IBEAM_GATEWAY_STARTUP": "60",
        "IBEAM_ERROR_SCREENSHOTS": "True",
    }

    import os
    conf_dir = os.path.join(os.path.dirname(__file__), "conf")
    volumes = {
        conf_dir: {"bind": "/srv/ibeam/conf", "mode": "rw"},
        os.path.join(conf_dir, "conf.yaml"): {"bind": "/srv/clientportal.gw/root/conf.yaml", "mode": "ro"},
    }

    try:
        container = docker_client.containers.run(
            image=IBEAM_IMAGE,
            name=name,
            detach=True,
            environment=env,
            ports={f"{IBEAM_INTERNAL_PORT}/tcp": port},
            volumes=volumes,
            restart_policy={"Name": "unless-stopped"},
        )
    except docker.errors.APIError as exc:
        raise HTTPException(status_code=500, detail=f"Docker error: {exc}") from exc

    sessions[account_id] = {
        "port": port,
        "container_name": name,
        "container_id": container.id,
        "status": "starting",
        "last_tickle": None,
    }

    return {
        "session_id": account_id,
        "port": port,
        "container_name": name,
        "status": "starting",
        "message": "Container started. ibeam login takes ~30-60 seconds.",
    }


@app.get("/sessions")
async def list_sessions() -> list[dict[str, Any]]:
    """Return all known sessions and their current status."""
    result = []
    for account_id, info in sessions.items():
        result.append(
            {
                "session_id": account_id,
                "port": info["port"],
                "container_name": info["container_name"],
                "status": info.get("status", "unknown"),
                "last_tickle": info.get("last_tickle"),
            }
        )
    return result


@app.get("/sessions/{account_id}/status")
async def session_status(account_id: str) -> dict[str, Any]:
    """Query the ibeam container's auth status endpoint directly."""
    if account_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    info = sessions[account_id]
    try:
        auth = await _get_auth_status(info["port"])
        sessions[account_id]["status"] = "authenticated" if auth.get("authenticated") else "not_authenticated"
        return {
            "session_id": account_id,
            "port": info["port"],
            "ibeam_response": auth,
        }
    except httpx.HTTPError as exc:
        sessions[account_id]["status"] = "unreachable"
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach ibeam container on port {info['port']}: {exc}",
        ) from exc


@app.delete("/sessions/{account_id}", status_code=200)
async def delete_session(account_id: str) -> dict[str, str]:
    """Stop and remove the ibeam container for the given account."""
    if account_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    info = sessions[account_id]
    name = info["container_name"]

    try:
        container = docker_client.containers.get(name)
        container.stop(timeout=10)
        container.remove()
    except docker.errors.NotFound:
        pass  # already gone — still clean up our state
    except docker.errors.APIError as exc:
        raise HTTPException(status_code=500, detail=f"Docker error: {exc}") from exc

    del sessions[account_id]
    return {"message": f"Session '{account_id}' stopped and removed."}


@app.api_route(
    "/sessions/{account_id}/proxy/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def proxy(account_id: str, path: str, request: Request) -> Response:
    """Transparent proxy to the ibeam container REST API."""
    if account_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    info = sessions[account_id]
    port = info["port"]
    target_url = f"{_ibeam_base_url(port)}/v1/api/{path}"

    # Forward query params
    if request.query_params:
        target_url = f"{target_url}?{request.query_params}"

    # Forward headers (strip host / content-length to avoid issues)
    forward_headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length")
    }

    body = await request.body()

    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        try:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=forward_headers,
                content=body,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Proxy error reaching ibeam on port {port}: {exc}",
            ) from exc

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers),
        media_type=resp.headers.get("content-type"),
    )


# ---------------------------------------------------------------------------
# Startup: re-discover any already-running ibeam containers
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def rediscover_containers() -> None:
    """On startup, re-populate sessions dict from running Docker containers."""
    try:
        containers = docker_client.containers.list(
            filters={"name": "ibeam-", "status": "running"}
        )
        for c in containers:
            name: str = c.name  # e.g. "ibeam-jibas-bot"
            if not name.startswith("ibeam-"):
                continue
            account_id = name[len("ibeam-"):]  # strip prefix

            # Get host port from container port bindings
            bindings = c.ports.get(f"{IBEAM_INTERNAL_PORT}/tcp")
            if not bindings:
                continue
            host_port = int(bindings[0]["HostPort"])

            if account_id not in sessions:
                sessions[account_id] = {
                    "port": host_port,
                    "container_name": name,
                    "container_id": c.id,
                    "status": "running",
                    "last_tickle": None,
                }
    except Exception as exc:  # noqa: BLE001
        print(f"[startup] Could not rediscover containers: {exc}")
