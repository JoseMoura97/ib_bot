from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import StrategyOut, StrategyPatch
from app.db.session import get_db
from app.models.strategy import Strategy


router = APIRouter()

def _plot_data_path() -> Path:
    return Path("/app/.cache/plot_data.json")


@router.get("", response_model=list[StrategyOut])
def list_strategies(db: Session = Depends(get_db)):
    rows = db.query(Strategy).order_by(Strategy.name.asc()).all()
    return [StrategyOut(name=r.name, enabled=r.enabled, config=r.config or {}) for r in rows]


@router.get("/catalog")
def catalog(db: Session = Depends(get_db)):
    """
    Return a merged catalog of known strategies:
    - metadata (category/subcategory/description/start_date/api_status/metrics) from QuiverSignals cache
    - enabled/config from DB (strategies table)
    - has_plot (whether a curve exists in .cache/plot_data.json)
    """
    # DB state
    db_rows = db.query(Strategy).all()
    db_map = {r.name: {"enabled": bool(r.enabled), "config": r.config or {}} for r in db_rows}

    # Plot availability
    has_plot: set[str] = set()
    try:
        p = _plot_data_path()
        if p.exists():
            payload = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("strategies"), dict):
                has_plot = set(payload["strategies"].keys())
    except Exception:
        has_plot = set()

    # Metadata
    try:
        from quiver_signals import QuiverSignals  # repo root

        meta_map = QuiverSignals.get_all_strategies() or {}
    except Exception:
        meta_map = {}

    names = sorted(set(meta_map.keys()) | set(db_map.keys()) | set(has_plot))

    rows = []
    for name in names:
        meta = meta_map.get(name) if isinstance(meta_map, dict) else {}
        meta = meta if isinstance(meta, dict) else {}
        state = db_map.get(name) or {"enabled": False, "config": {}}
        rows.append(
            {
                "name": name,
                "enabled": bool(state.get("enabled")),
                "config": state.get("config") or {},
                "has_plot": name in has_plot,
                "category": meta.get("category"),
                "subcategory": meta.get("subcategory"),
                "description": meta.get("description"),
                "api_status": meta.get("api_status"),
                "start_date": meta.get("start_date"),
            }
        )

    return {"count": len(rows), "rows": rows}


@router.patch("/{name}", response_model=StrategyOut)
def patch_strategy(name: str, body: StrategyPatch, db: Session = Depends(get_db)):
    s = db.query(Strategy).filter(Strategy.name == name).one_or_none()
    if s is None:
        s = Strategy(name=name, enabled=False, config={})
        db.add(s)

    if body.enabled is not None:
        s.enabled = bool(body.enabled)
    if body.config is not None:
        s.config = body.config

    db.commit()
    db.refresh(s)
    return StrategyOut(name=s.name, enabled=s.enabled, config=s.config or {})
