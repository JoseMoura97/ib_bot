from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from app.worker.celery_app import celery_app


router = APIRouter()


def _cache_path(name: str) -> Path:
    return Path("/app/.cache") / name


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    # Percent strings
    if s.endswith("%"):
        try:
            return float(s[:-1])
        except Exception:
            return None
    try:
        return float(s)
    except Exception:
        return None


def _load_last_validation_results() -> dict[str, Any] | None:
    path = _cache_path("last_validation_results.json")
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_plot_data() -> dict[str, Any] | None:
    path = _cache_path("plot_data.json")
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


@router.get("/strategies")
def metrics_strategies():
    """
    Return merged metrics for strategies:
    - `quiver`: Quiver reference metrics from `QuiverSignals.get_strategy_info` (best-effort)
    - `ours`: latest computed metrics from `.cache/last_validation_results.json` (preferred)
      falling back to `.cache/plot_data.json` if validation results are missing.
    """

    last_val = _load_last_validation_results()
    plot = _load_plot_data()

    ours_by_name: dict[str, dict[str, Any]] = {}
    benchmark = "SPY"
    generated_at = None
    if last_val and isinstance(last_val.get("strategies"), dict):
        benchmark = str(last_val.get("benchmark") or benchmark)
        generated_at = last_val.get("generated_at")
        for name, row in (last_val.get("strategies") or {}).items():
            if isinstance(row, dict):
                ours_by_name[str(name)] = row

    if not ours_by_name and plot and isinstance(plot.get("strategies"), dict):
        generated_at = plot.get("generated_at")
        bench = plot.get("benchmark") or {}
        if isinstance(bench, dict) and bench.get("name"):
            benchmark = str(bench.get("name"))
        for name, row in (plot.get("strategies") or {}).items():
            if not isinstance(row, dict):
                continue
            ours_by_name[str(name)] = {
                "status": "OK",
                "start_date": row.get("start_date"),
                "end_date": row.get("end_date"),
                "cagr": row.get("cagr"),
                "sharpe": row.get("sharpe"),
                "max_drawdown": row.get("max_drawdown"),
            }

    # Quiver metrics (best-effort; do not fail the endpoint if unavailable)
    quiver_by_name: dict[str, dict[str, Any]] = {}
    try:
        from quiver_signals import QuiverSignals  # repo root

        for name in ours_by_name.keys():
            info = QuiverSignals.get_strategy_info(name)
            if isinstance(info, dict):
                quiver_by_name[name] = info
    except Exception:
        quiver_by_name = {}

    # Build merged list
    rows: list[dict[str, Any]] = []
    for name in sorted(set(ours_by_name.keys()) | set(quiver_by_name.keys())):
        ours = ours_by_name.get(name) or {}
        quiver = quiver_by_name.get(name) or {}

        def diff(a: Any, b: Any) -> float | None:
            aa = _to_float(a)
            bb = _to_float(b)
            if aa is None or bb is None:
                return None
            return aa - bb

        rows.append(
            {
                "name": name,
                "category": quiver.get("category"),
                "subcategory": quiver.get("subcategory"),
                "benchmark": benchmark,
                "quiver": quiver,
                "ours": ours,
                "diffs": {
                    "cagr": diff(ours.get("cagr"), quiver.get("cagr")),
                    "sharpe": diff(ours.get("sharpe"), quiver.get("sharpe")),
                    "max_drawdown": diff(ours.get("max_drawdown"), quiver.get("max_drawdown")),
                    "beta": diff(ours.get("beta"), quiver.get("beta")),
                    "alpha": diff(ours.get("alpha"), quiver.get("alpha")),
                    "info_ratio": diff(ours.get("info_ratio"), quiver.get("info_ratio")),
                    "treynor": diff(ours.get("treynor"), quiver.get("treynor")),
                    "win_rate": diff(ours.get("win_rate"), quiver.get("win_rate")),
                    "trades": diff(ours.get("trades"), quiver.get("trades")),
                    "volatility": diff(ours.get("volatility"), quiver.get("volatility")),
                },
            }
        )

    return {"benchmark": benchmark, "generated_at": generated_at, "rows": rows}


@router.post("/strategies/refresh")
def refresh_validation_metrics(force: bool = True, max_age_hours: int = 24 * 7):
    """
    Enqueue a background refresh of `.cache/last_validation_results.json`.
    """
    celery_app.send_task(
        "refresh_validation_results_task",
        kwargs={"force": bool(force), "max_age_hours": int(max_age_hours)},
    )
    return {"queued": True}

