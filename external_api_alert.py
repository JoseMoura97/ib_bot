"""Drop-in helper: report a HARD external-API failure to the owning domain
manager via the conductor `api-failure` primitive.

Cross-project + cross-language: shells out to the conductor CLI, which resolves
the project's domain manager, coalesces per (project, service), logs to the PWA
/notifications feed, and (unless notify_only) dispatches the manager to triage.

Use ONLY at genuine infrastructure-failure sites (model retired, auth revoked,
endpoint gone, quota exhausted) — NOT routine misses or a single timeout.

For a failure of the CLAUDE LLM sub itself, pass notify_only=True (dispatching a
manager turn would use the same dead sub).

This file is intentionally self-contained (no conductor imports) so it can be
copied verbatim into any project repo. Fire-and-forget; never raises.
"""
from __future__ import annotations

import os
import subprocess
import time

_CONDUCTOR_BIN = os.environ.get(
    "CONDUCTOR_BIN",
    "/home/servidor/Desktop/cursor-projects/conductor/orchestrator/.venv/bin/conductor",
)
_CONDUCTOR_CWD = os.environ.get(
    "CONDUCTOR_CWD", "/home/servidor/Desktop/cursor-projects/conductor"
)
# Light local guard avoids spawning a CLI process on every loop while a failure
# persists; the real alert-coalescing is central (DB, --cooldown-min).
_LOCAL_GUARD_S = float(os.environ.get("EXTERNAL_API_LOCAL_GUARD_S", "60"))
_last: dict[str, float] = {}


def report_api_failure(
    project: str,
    service: str,
    detail: str,
    *,
    hint: str = "",
    notify_only: bool = False,
    cooldown_min: int = 30,
) -> None:
    """Report an external-API infrastructure failure. Never raises.

    project       project slug (resolves the owning domain manager; "" → top manager)
    service       stable provider key, e.g. 'anthropic', 'clob', 'ibkr', 'bingx'
    detail        one-line description of the failure
    hint          optional fix hint / where to look
    notify_only   only log to PWA /notifications; do NOT spend a manager triage turn
    cooldown_min  central suppression window for repeat (project,service) alerts
    """
    if not service or not detail:
        return
    now = time.time()
    if now - _last.get(service, 0.0) < _LOCAL_GUARD_S:
        return
    _last[service] = now

    args = [
        _CONDUCTOR_BIN, "api-failure",
        "--project", project or "",
        "--service", service,
        "--detail", detail,
        "--cooldown-min", str(int(cooldown_min)),
    ]
    if hint:
        args += ["--hint", hint]
    if notify_only:
        args.append("--notify-only")

    try:
        subprocess.Popen(
            args, cwd=_CONDUCTOR_CWD,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        pass
