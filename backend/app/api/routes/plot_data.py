from __future__ import annotations

import json
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from app.worker.celery_app import celery_app


router = APIRouter()


def _plot_data_path() -> Path:
    # Default to repo-root .cache when running in docker images (WORKDIR=/app)
    p = os.getenv("PLOT_DATA_PATH") or "/app/.cache/plot_data.json"
    return Path(p)


def _validation_results_path() -> Path:
    p = os.getenv("VALIDATION_RESULTS_PATH") or "/app/.cache/last_validation_results.json"
    return Path(p)


def _make_weekly_dates(start: datetime, end: datetime) -> list[str]:
    out: list[str] = []
    cur = start
    while cur <= end:
        out.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=7)
    return out


def _synthetic_curve(
    *,
    dates: list[str],
    annual_return: float,
    annual_vol: float,
    seed: int,
    base: float = 100.0,
) -> list[float]:
    """
    Quick synthetic curve generator (weekly lognormal-ish).
    annual_return and annual_vol are decimals (0.15 = 15%).
    """
    if not dates:
        return []
    rnd = random.Random(int(seed) & 0xFFFFFFFF)
    weeks = max(1, len(dates) - 1)
    mu_w = float(annual_return) / 52.0
    sigma_w = float(annual_vol) / (52.0**0.5)
    v = float(base)
    out = [v]
    prev = 0.0
    for _ in range(weeks):
        # Mild autocorrelation for realism
        shock = rnd.gauss(mu_w, sigma_w)
        shock = 0.7 * shock + 0.3 * prev
        prev = shock
        v *= max(0.01, 1.0 + shock)
        out.append(v)
    return out


def _build_sample_plot_data_from_validation(validation: dict, *, price_source: str) -> dict:
    """
    Build sample plot data quickly from validation metrics.
    This is a fallback when real plot_data generation produces an empty file.
    """
    now = datetime.utcnow()
    dates = _make_weekly_dates(datetime(2020, 1, 1), now)

    # SPY-ish benchmark (moderate growth + vol)
    spy_vals = _synthetic_curve(dates=dates, annual_return=0.15, annual_vol=0.18, seed=42, base=100.0)
    benchmark = {"name": "SPY", "dates": dates, "values": [round(x, 2) for x in spy_vals]}

    strategies: dict[str, dict] = {}
    strat_map = validation.get("strategies") if isinstance(validation, dict) else {}
    if not isinstance(strat_map, dict):
        strat_map = {}

    for name, metrics in strat_map.items():
        if not isinstance(name, str) or not name.strip():
            continue
        metrics = metrics if isinstance(metrics, dict) else {}
        if metrics.get("status") in {"ERROR", "FAILED"}:
            continue

        cagr_pct = float(metrics.get("cagr") or 0.0)
        sharpe = float(metrics.get("sharpe") or metrics.get("sharpe_ratio") or 0.5)
        max_dd_pct = float(metrics.get("max_drawdown") or -30.0)

        annual_return = cagr_pct / 100.0
        annual_vol = (annual_return / sharpe) if sharpe > 0 else 0.20
        annual_vol = max(0.01, min(1.0, float(annual_vol)))

        vals = _synthetic_curve(dates=dates, annual_return=annual_return, annual_vol=annual_vol, seed=hash(name), base=100.0)

        strategies[name] = {
            "name": name,
            "dates": dates,
            "values": [round(x, 2) for x in vals],
            "cagr": round(cagr_pct, 2),
            "sharpe": round(float(sharpe), 2),
            "max_drawdown": round(max_dd_pct, 2),
            "start_date": metrics.get("start_date"),
        }

    return {
        "generated_at": now.isoformat(),
        "data_source": "sample_from_validation",
        "price_source": price_source,
        "strategies": strategies,
        "benchmark": benchmark,
        "missing": False,
        "synthetic": True,
    }


@router.get("")
def get_plot_data():
    path = _plot_data_path()
    if not path.exists():
        # Return a small stub payload so the UI can still load end-to-end on fresh installs.
        # Users can click "Refresh plot data" to queue generation.
        return JSONResponse(
            {
                "generated_at": None,
                "data_source": "missing",
                "price_source": os.getenv("PRICE_SOURCE") or "unknown",
                "strategies": {},
                "benchmark": None,
                "missing": True,
                "detail": f"plot_data.json not found at {path}",
            }
        )
    # Read JSON so we can patch missing fields and fall back when empty.
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return JSONResponse(
            {
                "generated_at": None,
                "data_source": "error",
                "price_source": os.getenv("PRICE_SOURCE") or "unknown",
                "strategies": {},
                "benchmark": None,
                "missing": True,
                "detail": f"plot_data.json unreadable: {type(e).__name__}: {e}",
            }
        )

    if not isinstance(payload, dict):
        payload = {"generated_at": None, "strategies": {}, "benchmark": None}

    payload.setdefault("data_source", os.getenv("PLOT_DATA_SOURCE") or "unknown")
    payload.setdefault("price_source", os.getenv("PRICE_SOURCE") or "unknown")
    payload.setdefault("strategies", {})
    payload.setdefault("benchmark", None)

    # REMOVED: Synthetic fallback generation
    # Users should only see real data. If plot_data.json is empty, they need to click "Update Data".

    return JSONResponse(payload)


@router.post("/refresh")
def refresh_plot_data(force: bool = True, max_age_hours: int = 24):
    """
    Enqueue a background refresh of .cache/plot_data.json.
    """
    ar = celery_app.send_task("refresh_plot_data_task", kwargs={"force": bool(force), "max_age_hours": int(max_age_hours)})
    return {"queued": True, "task_id": getattr(ar, "id", None)}


@router.get("/refresh/{task_id}")
def refresh_plot_data_status(task_id: str):
    """
    Check Celery task status for a plot-data refresh.
    """
    r = celery_app.AsyncResult(task_id)
    state = getattr(r, "state", None) or "UNKNOWN"
    detail = None
    progress = None
    
    if state == "PROGRESS":
        # Extract progress metadata
        try:
            info = getattr(r, "info", None)
            if isinstance(info, dict):
                progress = {
                    "stage": info.get("stage", "running"),
                    "percent": info.get("percent", 0),
                    "strategies_count": info.get("strategies_count"),
                }
        except Exception:
            pass
    elif state in {"FAILURE", "REVOKED"}:
        try:
            detail = str(getattr(r, "result", None))
        except Exception:
            detail = None
    
    return {"task_id": task_id, "state": state, "detail": detail, "progress": progress}

