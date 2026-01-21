from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.portfolio import PortfolioStrategy
from app.models.result import PortfolioResult
from app.models.result import StrategyResult
from app.models.run import Run
from app.services.portfolio_backtest import portfolio_backtest_holdings_union, portfolio_backtest_nav_blend
from app.worker.celery_app import celery_app


def _parse_dt(s: str):
    import pandas as pd

    return pd.to_datetime(s).to_pydatetime()


def _db() -> Session:
    return SessionLocal()


@celery_app.task(name="portfolio_backtest_task")
def portfolio_backtest_task(run_id: str) -> None:
    db = _db()
    try:
        r = db.query(Run).filter(Run.id == run_id).one_or_none()
        if r is None:
            return
        r.status = "RUNNING"
        r.started_at = datetime.utcnow()
        r.progress = {"stage": "starting"}
        db.commit()

        params = r.params or {}
        portfolio_id = params.get("portfolio_id")
        mode = params.get("mode")
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        transaction_cost_bps = float(params.get("transaction_cost_bps") or 0.0)

        # Resolve strategy list/weights from params (captured at run creation)
        strategies = params.get("strategies") or []
        strategy_names = [s.get("name") for s in strategies if s.get("name")]
        strategy_weights = {s.get("name"): float(s.get("weight") or 0.0) for s in strategies if s.get("name")}

        r.progress = {"stage": "running", "mode": mode, "n_strategies": len(strategy_names)}
        db.commit()

        if mode == "nav_blend":
            out = portfolio_backtest_nav_blend(
                strategy_names=strategy_names,
                strategy_weights=strategy_weights,
                start_date=start_date,
                end_date=end_date,
                transaction_cost_bps=transaction_cost_bps,
            )
        elif mode == "holdings_union":
            out = portfolio_backtest_holdings_union(
                strategy_names=strategy_names,
                strategy_weights=strategy_weights,
                start_date=start_date,
                end_date=end_date,
                transaction_cost_bps=transaction_cost_bps,
            )
        else:
            out = {"error": f"Unknown mode: {mode}"}

        if "error" in out:
            r.status = "ERROR"
            r.error = str(out.get("error"))
            r.progress = {"stage": "error"}
            r.finished_at = datetime.utcnow()
            db.commit()
            return

        metrics = out.get("portfolio") or {}
        artifacts = {"equity_curve": out.get("equity_curve"), "strategy_results": out.get("strategy_results")}

        pr = PortfolioResult(
            run_id=r.id,
            portfolio_id=portfolio_id,
            mode=mode,
            metrics=metrics,
            artifacts=artifacts,
        )
        db.add(pr)

        r.status = "SUCCESS"
        r.progress = {"stage": "done"}
        r.finished_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        # Ensure the run doesn't get stuck in RUNNING if the worker crashes mid-task.
        try:
            r = db.query(Run).filter(Run.id == run_id).one_or_none()
            if r is not None:
                r.status = "ERROR"
                r.error = f"{type(e).__name__}: {e}"
                r.progress = {"stage": "error"}
                r.finished_at = datetime.utcnow()
                db.commit()
        except Exception:
            # Last resort: swallow to avoid crashing the worker process.
            pass
    finally:
        db.close()


@celery_app.task(name="validation_task")
def validation_task(run_id: str) -> None:
    db = _db()
    try:
        r = db.query(Run).filter(Run.id == run_id).one_or_none()
        if r is None:
            return
        r.status = "RUNNING"
        r.started_at = datetime.utcnow()
        r.progress = {"stage": "starting"}
        db.commit()

        if not settings.quiver_api_key:
            r.status = "ERROR"
            r.error = "QUIVER_API_KEY not configured"
            r.progress = {"stage": "error"}
            r.finished_at = datetime.utcnow()
            db.commit()
            return

        params = r.params or {}
        strategies = params.get("strategies") or []
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        lookback_override = params.get("lookback_days_override")
        transaction_cost_bps = float(params.get("transaction_cost_bps") or 0.0)

        from rebalancing_backtest_engine import RebalancingBacktestEngine  # repo root
        from app.services.serialization import equity_curve_to_records

        bt = RebalancingBacktestEngine(
            quiver_api_key=settings.quiver_api_key,
            initial_capital=100000.0,
            transaction_cost_bps=float(transaction_cost_bps),
            price_source=settings.price_source,
        )

        for i, name in enumerate(strategies):
            r.progress = {"stage": "running", "current": name, "i": i + 1, "n": len(strategies)}
            db.commit()

            out = bt.run_rebalancing_backtest(
                strategy_name=name,
                start_date=_parse_dt(start_date) if start_date else datetime.utcnow(),
                end_date=_parse_dt(end_date) if end_date else datetime.utcnow(),
                lookback_days_override=int(lookback_override) if lookback_override else None,
            )

            if "error" in out:
                metrics = {"status": "ERROR", "error": str(out.get("error"))}
                artifacts = {}
            else:
                metrics = {
                    "status": "OK",
                    "cagr": out.get("cagr"),
                    "sharpe_ratio": out.get("sharpe_ratio"),
                    "max_drawdown": out.get("max_drawdown"),
                    "total_return": out.get("total_return"),
                    "final_value": out.get("final_value"),
                    "beta": out.get("beta"),
                    "alpha": out.get("alpha"),
                    "info_ratio": out.get("info_ratio"),
                    "treynor": out.get("treynor"),
                    "win_rate": out.get("win_rate"),
                    "trades": out.get("trades"),
                }
                artifacts = {"equity_curve": equity_curve_to_records(out.get("equity_curve"))}

            db.add(StrategyResult(run_id=r.id, strategy_name=name, metrics=metrics, artifacts=artifacts))
            db.commit()

        r.status = "SUCCESS"
        r.progress = {"stage": "done"}
        r.finished_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        try:
            r = db.query(Run).filter(Run.id == run_id).one_or_none()
            if r is not None:
                r.status = "ERROR"
                r.error = f"{type(e).__name__}: {e}"
                r.progress = {"stage": "error"}
                r.finished_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


@celery_app.task(name="refresh_plot_data_task")
def refresh_plot_data_task(force: bool = True, max_age_hours: int = 24) -> None:
    """
    Refresh `.cache/plot_data.json` by running `generate_plot_data.py`.

    Notes:
    - This is file-based persistence (mounted volume recommended).
    - It may take a while depending on strategies and price source.
    """
    import subprocess
    import sys

    cmd = [
        sys.executable,
        "generate_plot_data.py",
        "--max-age-hours",
        str(int(max_age_hours)),
    ]
    if force:
        cmd.append("--force")

    # Run in repo root (WORKDIR is /app in docker images)
    subprocess.run(cmd, check=False)


@celery_app.task(name="refresh_validation_results_task")
def refresh_validation_results_task(force: bool = True, max_age_hours: int = 24 * 7) -> None:
    """
    Refresh `.cache/last_validation_results.json` by running `validate_quiver_replication.py`.

    Notes:
    - Requires QUIVER_API_KEY to produce real Quiver-vs-ours validation.
    - The underlying script writes progress checkpoints during long runs.
    """
    import json
    import os
    import subprocess
    import sys
    from datetime import datetime, timezone
    from pathlib import Path

    out_path = Path("/app/.cache/last_validation_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if (not force) and out_path.exists():
        age_seconds = max(
            0.0,
            (datetime.now(timezone.utc) - datetime.fromtimestamp(out_path.stat().st_mtime, tz=timezone.utc)).total_seconds(),
        )
        if age_seconds <= float(max_age_hours) * 3600.0:
            return

    if not os.getenv("QUIVER_API_KEY"):
        payload = {
            "benchmark": "SPY",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "error": "QUIVER_API_KEY not configured (skipping validation refresh)",
            "strategies": {},
        }
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return

    cmd = [sys.executable, "validate_quiver_replication.py"]
    subprocess.run(cmd, check=False)

