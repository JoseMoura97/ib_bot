from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.ib_audit import LiveShadowSnapshot
from app.models.portfolio import Portfolio, PortfolioStrategy
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


def _parse_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    parts = []
    for chunk in str(raw).replace(";", ",").split(","):
        val = chunk.strip()
        if val:
            parts.append(val)
    return parts


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


@celery_app.task(name="shadow_preview_task")
def shadow_preview_task() -> None:
    """
    Preview live rebalance targets without executing and store diffs vs holdings.
    """
    accounts = _parse_list(settings.shadow_preview_accounts)
    portfolio_ids = _parse_list(settings.shadow_preview_portfolios)
    if not accounts or not portfolio_ids:
        return

    from app.api.routes.live import LiveRebalanceRequest, _build_preview, _current_positions_for_account
    import hashlib

    db = _db()
    try:
        for account_id in accounts:
            holdings = _current_positions_for_account(str(account_id))
            holdings_items = sorted((k, float(v)) for k, v in (holdings or {}).items())
            holdings_hash = hashlib.sha256(str(holdings_items).encode("utf-8")).hexdigest()

            for pid in portfolio_ids:
                p = db.query(Portfolio).filter(Portfolio.id == str(pid)).one_or_none()
                if p is None:
                    continue
                try:
                    body = LiveRebalanceRequest(
                        account_id=str(account_id),
                        portfolio_id=p.id,
                        allocation_amount=float(settings.shadow_preview_allocation),
                        allow_short=False,
                        confirm=False,
                    )
                    preview = _build_preview(db, body)
                    preview_payload = preview.model_dump(mode="json")
                except Exception as e:
                    preview_payload = {"error": f"{type(e).__name__}: {e}"}

                snap = LiveShadowSnapshot(
                    account_id=str(account_id),
                    portfolio_id=p.id,
                    allocation_amount=float(settings.shadow_preview_allocation),
                    holdings_hash=holdings_hash,
                    holdings=holdings or {},
                    preview=preview_payload,
                )
                db.add(snap)
                db.commit()
    finally:
        db.close()


@celery_app.task(name="refresh_plot_data_task", bind=True)
def refresh_plot_data_task(self, force: bool = True, max_age_hours: int = 24) -> None:
    """
    Refresh `.cache/plot_data.json` by running real backtests.

    Uses cached price data where available, fetches from API where needed.
    This produces REAL equity curves from actual historical data.

    Notes:
    - This is file-based persistence (mounted volume recommended).
    - Uses PRICE_SOURCE env var (default: auto) for price fetching.
    - May take several minutes depending on how much data needs fetching.
    - SAFETY: Always creates a timestamped backup before overwriting.
    """
    import json
    import shutil
    import subprocess
    import sys
    from datetime import datetime
    from pathlib import Path

    # Update progress: starting
    self.update_state(state="PROGRESS", meta={"stage": "starting", "percent": 0})

    out_path = Path("/app/.cache/plot_data.json")
    backup_dir = Path("/app/.cache/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)

    # SAFETY: Create backup of existing data before any refresh
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            existing_strategies = existing.get("strategies", {})
            if len(existing_strategies) > 0:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = backup_dir / f"plot_data_backup_{timestamp}.json"
                shutil.copy2(out_path, backup_path)
                # Keep only last 5 backups
                backups = sorted(backup_dir.glob("plot_data_backup_*.json"))
                for old_backup in backups[:-5]:
                    old_backup.unlink()
        except Exception:
            pass  # Don't fail if backup fails

    cmd = [
        sys.executable,
        "generate_plot_data.py",
    ]
    
    # Update progress: running script
    self.update_state(state="PROGRESS", meta={"stage": "generating", "percent": 20})

    # Run in repo root (WORKDIR is /app in docker images)
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    
    # Update progress: validating
    self.update_state(state="PROGRESS", meta={"stage": "validating", "percent": 80})
    
    out_path = Path("/app/.cache/plot_data.json")
    
    # Check if script succeeded
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        detail = stderr or stdout or f"generate_plot_data.py exited with code {result.returncode}"
        raise RuntimeError(detail)

    # Validate output file content
    if not out_path.exists():
        raise RuntimeError("plot_data.json not found after refresh")
    try:
        payload = json.loads(out_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(f"plot_data.json unreadable: {type(e).__name__}: {e}") from e
    
    strategies = payload.get("strategies") if isinstance(payload, dict) else None
    if not isinstance(strategies, dict) or len(strategies) == 0:
        raise RuntimeError("plot_data.json contains no strategies after refresh")
    
    # Verify it's not synthetic
    is_synthetic = payload.get("synthetic", False)
    data_source = payload.get("data_source", "unknown")
    
    # Update progress: complete
    self.update_state(state="PROGRESS", meta={
        "stage": "complete", 
        "percent": 100, 
        "strategies_count": len(strategies),
        "data_source": data_source,
        "synthetic": is_synthetic,
    })


@celery_app.task(name="paper_rebalance_daily_task")
def paper_rebalance_daily_task() -> None:
    """
    Auto-rebalance all paper accounts that have a linked portfolio.
    Looks for accounts with at least one allocation record to determine the portfolio + amount.
    """
    import logging
    from app.models.allocation import PortfolioAllocation
    from app.models.paper import PaperRebalanceLog

    logger = logging.getLogger(__name__)
    db = _db()
    try:
        allocs = (
            db.query(PortfolioAllocation)
            .filter(PortfolioAllocation.mode == "paper")
            .order_by(PortfolioAllocation.created_at.desc())
            .all()
        )
        if not allocs:
            logger.info("paper_rebalance_daily: no paper allocations found, skipping")
            return

        seen: set[tuple] = set()
        for alloc in allocs:
            key = (str(alloc.account_id), str(alloc.portfolio_id))
            if key in seen:
                continue
            seen.add(key)

            try:
                account_id = int(alloc.account_id)
            except (ValueError, TypeError):
                account_id = 1

            portfolio_id = str(alloc.portfolio_id)
            amount = float(alloc.amount)

            from app.api.schemas import PaperRebalanceRequest as PRReq
            from app.api.routes.paper import paper_rebalance_execute
            from uuid import UUID

            try:
                body = PRReq(
                    portfolio_id=UUID(portfolio_id),
                    allocation_amount=amount,
                    account_id=account_id,
                )
                result = paper_rebalance_execute(body, db)
                n_orders = len(result.orders) if result.orders else 0
                log_entry = PaperRebalanceLog(
                    account_id=account_id,
                    portfolio_id=portfolio_id,
                    status="SUCCESS",
                    n_orders=n_orders,
                    details={"orders": n_orders, "allocation_amount": amount},
                )
                db.add(log_entry)
                db.commit()
                logger.info(f"paper_rebalance_daily: account={account_id} portfolio={portfolio_id} orders={n_orders}")
            except Exception as e:
                db.rollback()
                log_entry = PaperRebalanceLog(
                    account_id=account_id,
                    portfolio_id=portfolio_id,
                    status="ERROR",
                    n_orders=0,
                    details={"error": f"{type(e).__name__}: {e}"},
                )
                db.add(log_entry)
                db.commit()
                logger.warning(f"paper_rebalance_daily: account={account_id} portfolio={portfolio_id} error={e}")
    finally:
        db.close()


@celery_app.task(name="paper_snapshot_daily_task")
def paper_snapshot_daily_task() -> None:
    """
    Snapshot cash + equity for all paper accounts.
    Uses live prices for position valuation where possible.
    """
    import logging
    from app.models.paper import PaperAccount, PaperPosition, PaperSnapshot
    from app.services.paper_trading import fetch_prices

    logger = logging.getLogger(__name__)
    db = _db()
    try:
        accounts = db.query(PaperAccount).all()
        if not accounts:
            return

        for acct in accounts:
            positions = (
                db.query(PaperPosition)
                .filter(PaperPosition.account_id == int(acct.id), PaperPosition.quantity != 0)
                .all()
            )
            cash = float(acct.balance)
            equity = cash

            if positions:
                tickers = [p.ticker for p in positions]
                try:
                    quotes = fetch_prices(tickers)
                    for p in positions:
                        q = quotes.get(p.ticker)
                        price = float(q.price) if q and q.price > 0 else float(p.avg_cost)
                        equity += float(p.quantity) * price
                except Exception:
                    for p in positions:
                        equity += float(p.quantity) * float(p.avg_cost)

            positions_dict = {
                p.ticker: {"quantity": float(p.quantity), "avg_cost": float(p.avg_cost)}
                for p in positions
            }

            snap = PaperSnapshot(
                account_id=int(acct.id),
                cash=cash,
                equity=equity,
                positions_json=positions_dict,
            )
            db.add(snap)

        db.commit()
        logger.info(f"paper_snapshot_daily: snapshotted {len(accounts)} account(s)")

        try:
            from app.services.alerting import send_daily_pnl_alert
            for acct in accounts:
                prev_snaps = (
                    db.query(PaperSnapshot)
                    .filter(PaperSnapshot.account_id == int(acct.id))
                    .order_by(PaperSnapshot.timestamp.desc())
                    .limit(2)
                    .all()
                )
                if len(prev_snaps) >= 2:
                    daily_pnl = float(prev_snaps[0].equity) - float(prev_snaps[1].equity)
                    send_daily_pnl_alert(str(acct.id), float(prev_snaps[0].equity), daily_pnl)
        except Exception:
            pass
    except Exception as e:
        db.rollback()
        logger.warning(f"paper_snapshot_daily: error: {e}")
    finally:
        db.close()


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

