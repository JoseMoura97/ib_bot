from __future__ import annotations

from datetime import datetime, timedelta
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
from app.services.rebalance_freq import is_due, portfolio_native_frequency, resolve_frequency
from app.worker.celery_app import celery_app


def _portfolio_native(db: Session, portfolio_id: str) -> str:
    """Native cadence for a portfolio = fastest enabled constituent strategy."""
    names = [
        s.strategy_name
        for s in db.query(PortfolioStrategy)
        .filter(PortfolioStrategy.portfolio_id == UUID(portfolio_id))
        .all()
        if s.enabled
    ]
    return portfolio_native_frequency(names)


def _paper_last_rebalance(db: Session, account_id: int, portfolio_id: str):
    """Timestamp of the last SUCCESSFUL paper rebalance for this allocation, or None."""
    from app.models.paper import PaperRebalanceLog

    row = (
        db.query(PaperRebalanceLog)
        .filter(
            PaperRebalanceLog.account_id == account_id,
            PaperRebalanceLog.portfolio_id == portfolio_id,
            PaperRebalanceLog.status == "SUCCESS",
        )
        .order_by(PaperRebalanceLog.timestamp.desc())
        .first()
    )
    return row.timestamp if row else None


def _live_last_rebalance(db: Session, account_id: str, portfolio_id: str):
    """Timestamp of the last OK live execute for this allocation, or None."""
    from app.models.ib_audit import LiveRebalanceAudit

    row = (
        db.query(LiveRebalanceAudit)
        .filter(
            LiveRebalanceAudit.account_id == account_id,
            LiveRebalanceAudit.portfolio_id == UUID(portfolio_id),
            LiveRebalanceAudit.action == "execute",
            LiveRebalanceAudit.status == "OK",
        )
        .order_by(LiveRebalanceAudit.created_at.desc())
        .first()
    )
    return row.created_at if row else None


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
        # If the exception came from a failed commit (e.g. non-serializable
        # artifacts), the session is in aborted-transaction state — we MUST
        # rollback before issuing new queries, otherwise every subsequent
        # statement silently fails and the row stays at RUNNING forever.
        try:
            db.rollback()
        except Exception:
            pass
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


@celery_app.task(
    name="shadow_preview_task",
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_backoff_max=300,
    max_retries=2,
)
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


@celery_app.task(
    name="refresh_plot_data_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_backoff_max=600,
    max_retries=3,
)
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

    # SAFETY: Create backup of existing data before any refresh.
    # `prior_strategy_count` is used post-generation to reject partial runs
    # (e.g. a live-API run that rate-limits mid-way and only completes a
    # subset) from clobbering a complete file.
    prior_strategy_count = 0
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            existing_strategies = existing.get("strategies", {})
            prior_strategy_count = len(existing_strategies)
            if prior_strategy_count > 0:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = backup_dir / f"plot_data_backup_{timestamp}.json"
                shutil.copy2(out_path, backup_path)
                # Keep only last 5 backups
                backups = sorted(backup_dir.glob("plot_data_backup_*.json"))
                for old_backup in backups[:-5]:
                    old_backup.unlink()
        except Exception:
            pass  # Don't fail if backup fails

    # Keep live price-fetching (this nightly run is also what warms the
    # price cache — there is no separate price-warming task). `--yes` skips
    # the api_caution confirmation prompt for unattended execution. If a run
    # rate-limits mid-way and produces partial output, the partial-run guard
    # in _validate_output rejects it and restores the backup.
    cmd = [
        sys.executable,
        "generate_plot_data.py",
        "--yes",
    ]

    self.update_state(state="PROGRESS", meta={"stage": "generating", "percent": 20})

    result = subprocess.run(cmd, check=False, capture_output=True, text=True)

    self.update_state(state="PROGRESS", meta={"stage": "validating", "percent": 80})

    out_path = Path("/app/.cache/plot_data.json")

    def _restore_backup() -> None:
        """Restore the most recent non-empty backup if available."""
        backups = sorted(backup_dir.glob("plot_data_backup_*.json"), reverse=True)
        for bp in backups:
            try:
                bdata = json.loads(bp.read_text(encoding="utf-8"))
                if len(bdata.get("strategies", {})) > 0:
                    shutil.copy2(bp, out_path)
                    return
            except Exception:
                continue

    def _validate_output() -> tuple[dict, bool]:
        """Return (payload, is_valid). Restores backup on failure."""
        if not out_path.exists():
            _restore_backup()
            raise RuntimeError("plot_data.json not found after refresh; backup restored")
        try:
            payload = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception as e:
            _restore_backup()
            raise RuntimeError(f"plot_data.json unreadable ({e}); backup restored") from e
        strats = payload.get("strategies") if isinstance(payload, dict) else None
        if not isinstance(strats, dict) or len(strats) == 0:
            _restore_backup()
            raise RuntimeError("plot_data.json has 0 strategies; backup restored")
        # Partial-run guard: a refresh that completes far fewer strategies
        # than the prior file almost always means generation died mid-way
        # (rate-limit, crash). Don't let a partial result clobber a complete
        # one — restore the backup instead. 10% shrink tolerance covers
        # legitimate registry changes.
        if prior_strategy_count > 0 and len(strats) < prior_strategy_count * 0.9:
            _restore_backup()
            raise RuntimeError(
                f"plot_data.json has {len(strats)} strategies vs prior "
                f"{prior_strategy_count} (partial run); backup restored"
            )
        return payload, True

    if result.returncode != 0:
        _restore_backup()
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        detail = stderr or stdout or f"generate_plot_data.py exited with code {result.returncode}"
        raise RuntimeError(f"{detail}; backup restored")

    if not out_path.exists():
        _restore_backup()
        if not out_path.exists():
            raise RuntimeError("generate_plot_data.py produced no output and no backup available")

    payload, _ = _validate_output()

    strategies = payload.get("strategies", {})
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


@celery_app.task(
    name="paper_rebalance_daily_task",
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_backoff_max=300,
    max_retries=1,
)
def paper_rebalance_daily_task() -> None:
    """
    Auto-rebalance paper allocations that are DUE per their chosen cadence.

    Runs daily, but each allocation only rebalances when its frequency says so
    (a weekly book ~every 7 days, a quarterly one ~every 90), so it tracks the
    strategy's native cadence instead of trading every single day. The chosen
    frequency is stored on the allocation ("follow" → the portfolio's native
    cadence; "manual" → never auto-rebalanced).
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

            # Skip unless this allocation's cadence is due (or it's manual-only).
            native = _portfolio_native(db, portfolio_id)
            resolved = resolve_frequency(alloc.rebalance_frequency, native)
            last = _paper_last_rebalance(db, account_id, portfolio_id)
            if not is_due(last, resolved):
                logger.info(
                    f"paper_rebalance_daily: account={account_id} portfolio={portfolio_id} "
                    f"not due (freq={resolved}, last={last}), skipping"
                )
                continue

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
                    details={"orders": n_orders, "allocation_amount": amount, "frequency": resolved},
                )
                db.add(log_entry)
                db.commit()
                logger.info(
                    f"paper_rebalance_daily: account={account_id} portfolio={portfolio_id} "
                    f"freq={resolved} orders={n_orders}"
                )
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


@celery_app.task(
    name="live_rebalance_scheduled_task",
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_backoff_max=300,
    max_retries=1,
)
def live_rebalance_scheduled_task() -> None:
    """
    Unattended LIVE auto-rebalance — OFF unless LIVE_AUTO_REBALANCE=true.

    Only allocations whose cadence is due are executed, each through the SAME
    hard gates as a manual live rebalance (idempotency, halt, account allowlist,
    market-open, circuit breaker, NLV cap). "manual" allocations are never
    auto-rebalanced. A per-day idempotency key prevents same-day double-execution.
    """
    import logging
    from datetime import date
    from app.models.allocation import PortfolioAllocation

    logger = logging.getLogger(__name__)

    if not settings.live_auto_rebalance:
        logger.info("live_rebalance_scheduled: LIVE_AUTO_REBALANCE off, skipping")
        return
    if not settings.enable_live_trading or settings.live_dry_run:
        logger.info("live_rebalance_scheduled: live trading not armed (enable/dry_run), skipping")
        return
    if settings.trading_halt:
        logger.info("live_rebalance_scheduled: trading halted, skipping")
        return

    from app.services.market_calendar import market_is_open

    is_open, reason = market_is_open(settings.market_calendar)
    if not is_open:
        logger.info(f"live_rebalance_scheduled: market closed ({reason}), skipping")
        return

    from app.api.routes.live import LiveRebalanceRequest, execute_live_rebalance_core

    db = _db()
    try:
        allocs = (
            db.query(PortfolioAllocation)
            .filter(PortfolioAllocation.mode == "live")
            .order_by(PortfolioAllocation.created_at.desc())
            .all()
        )
        seen: set[tuple] = set()
        for alloc in allocs:
            key = (str(alloc.account_id), str(alloc.portfolio_id))
            if key in seen:
                continue
            seen.add(key)

            portfolio_id = str(alloc.portfolio_id)
            native = _portfolio_native(db, portfolio_id)
            resolved = resolve_frequency(alloc.rebalance_frequency, native)
            last = _live_last_rebalance(db, str(alloc.account_id), portfolio_id)
            if not is_due(last, resolved):
                logger.info(f"live_rebalance_scheduled: {key} not due (freq={resolved}), skipping")
                continue

            body = LiveRebalanceRequest(
                account_id=str(alloc.account_id),
                portfolio_id=UUID(portfolio_id),
                allocation_amount=float(alloc.amount),
                max_orders=200,
                allow_short=True,
                confirm=True,
            )
            idem = f"auto-{alloc.account_id}-{portfolio_id}-{date.today().isoformat()}"
            try:
                execute_live_rebalance_core(db, body, idem)
                logger.info(f"live_rebalance_scheduled: executed {key} freq={resolved}")
            except Exception as e:
                # Benign cases (no due trades, market edge) raise HTTPException too;
                # log and move on rather than failing the whole sweep.
                logger.warning(f"live_rebalance_scheduled: {key} not executed: {type(e).__name__}: {e}")
    finally:
        db.close()


@celery_app.task(
    name="paper_snapshot_daily_task",
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_backoff_max=300,
    max_retries=2,
)
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


@celery_app.task(
    name="reconcile_stuck_executions_task",
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_backoff_max=120,
    max_retries=2,
)
def reconcile_stuck_executions_task() -> None:
    """
    Phase 2: Flip LiveExecutionRequest rows that have been IN_PROGRESS for more
    than 10 minutes to FAILED, preventing the idempotency table from locking out
    retries after a worker crash or API restart mid-execute.
    """
    import logging
    from datetime import timezone
    from app.models.ib_audit import LiveExecutionRequest

    logger = logging.getLogger(__name__)
    db = _db()
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=10)
        stuck = (
            db.query(LiveExecutionRequest)
            .filter(
                LiveExecutionRequest.status == "IN_PROGRESS",
                LiveExecutionRequest.created_at < cutoff,
            )
            .all()
        )
        if not stuck:
            return
        for row in stuck:
            row.status = "FAILED"
            row.error = "reconciled: IN_PROGRESS exceeded 10-minute TTL (worker crash or restart)"
            row.result = {"error": row.error}
        db.commit()
        logger.warning(
            "reconcile_stuck_executions: reset %d stuck IN_PROGRESS row(s) to FAILED",
            len(stuck),
        )
    finally:
        db.close()


@celery_app.task(
    name="reconcile_stuck_runs_task",
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_backoff_max=120,
    max_retries=2,
)
def reconcile_stuck_runs_task(max_age_minutes: int = 480) -> None:
    """
    Reset `runs` rows that have been RUNNING longer than `max_age_minutes`
    to ERROR. These are orphans from worker crashes / SIGKILL'd containers
    where the task's exception handler never got to run.

    TTL is 8 hours — large backtests (many strategies × long date range) can
    legitimately run for several hours, so a 60-minute TTL was too aggressive.
    """
    import logging

    logger = logging.getLogger(__name__)
    db = _db()
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)
        stuck = (
            db.query(Run)
            .filter(
                Run.status == "RUNNING",
                Run.started_at < cutoff,
            )
            .all()
        )
        if not stuck:
            return
        for r in stuck:
            r.status = "ERROR"
            r.error = (
                f"reconciled: RUNNING exceeded {max_age_minutes}-minute TTL "
                "(worker crash or restart)"
            )
            r.progress = {"stage": "error", "reason": "orphaned"}
            r.finished_at = datetime.utcnow()
        db.commit()
        logger.warning(
            "reconcile_stuck_runs: reset %d stuck RUNNING row(s) to ERROR",
            len(stuck),
        )
    finally:
        db.close()


@celery_app.task(
    name="refresh_validation_results_task",
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_backoff_max=600,
    max_retries=3,
)
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



# ---------------------------------------------------------------------------
# Point-in-time alternative-data snapshots (the compounding archive)
# ---------------------------------------------------------------------------


def _altdata_store(db, source: str, records: list, as_of) -> str:
    """Store one source's vintage for `as_of`, deduping by content hash.

    If the latest stored snapshot for this source has the same content hash,
    we store a metadata-only row (payload NULL) to avoid duplicating big blobs.
    """
    import hashlib
    import json as _json
    from app.models.altdata import AltDataSnapshot

    body = _json.dumps(records, default=str, sort_keys=True)
    chash = hashlib.sha256(body.encode("utf-8")).hexdigest()

    # already captured today? (idempotent on re-run)
    existing = (
        db.query(AltDataSnapshot)
        .filter(AltDataSnapshot.source == source, AltDataSnapshot.as_of_date == as_of)
        .one_or_none()
    )
    if existing is not None:
        return "exists"

    prev = (
        db.query(AltDataSnapshot)
        .filter(AltDataSnapshot.source == source)
        .order_by(AltDataSnapshot.as_of_date.desc())
        .first()
    )
    unchanged = prev is not None and prev.content_hash == chash
    snap = AltDataSnapshot(
        source=source,
        as_of_date=as_of,
        n_rows=len(records),
        content_hash=chash,
        payload=None if unchanged else records,  # metadata-only when unchanged
    )
    db.add(snap)
    return "unchanged" if unchanged else "stored"


def _df_records(df, cap: int = 20000) -> list:
    """DataFrame -> JSON-safe records (capped)."""
    try:
        import pandas as pd  # noqa: F401
        if df is None or getattr(df, "empty", True):
            return []
        d = df.head(cap).copy()
        for c in d.columns:
            if str(d[c].dtype).startswith("datetime"):
                d[c] = d[c].astype(str)
        return d.to_dict(orient="records")
    except Exception:
        return []


@celery_app.task(name="altdata_snapshot_daily_task")
def altdata_snapshot_daily_task() -> None:
    """Capture a daily point-in-time vintage of each free alt-data source.

    Failure-safe: every source is wrapped; one source failing never aborts the
    others or the task. This is the only un-replicable, compounding asset — it
    must run every day going forward.
    """
    import logging
    from datetime import date as _date

    logger = logging.getLogger(__name__)
    db = _db()
    as_of = _date.today()
    summary: dict[str, str] = {}
    try:
        # 1) Congressional trades (bulk full history) — the flagship signal
        try:
            import quiver_engine
            eng = quiver_engine.QuiverStrategyEngine(api_key=settings.quiver_api_key or "")
            df = eng._get_bulk_congress_data()
            summary["congress_trades"] = _altdata_store(db, "congress_trades", _df_records(df), as_of)
        except Exception as e:
            summary["congress_trades"] = f"err:{type(e).__name__}"

        # 2) FINRA off-exchange short volume (today's file)
        try:
            from finra_short import FinraShortVolume
            fs = FinraShortVolume()
            df = fs.get_window(end_date=datetime.utcnow(), lookback_days=1)
            summary["finra_offexch_short"] = _altdata_store(db, "finra_offexch_short", _df_records(df), as_of)
        except Exception as e:
            summary["finra_offexch_short"] = f"err:{type(e).__name__}"

        # 3) Latest 13F holdings for tracked funds (free EDGAR)
        try:
            import sec_edgar
            sec = sec_edgar.SECEdgarClient() if hasattr(sec_edgar, "SECEdgarClient") else None
            for fund in ["Scion Asset Management", "Berkshire Hathaway"]:
                try:
                    if sec is None:
                        break
                    hdf = sec.get_latest_holdings(fund)
                    key = "13f_" + fund.lower().replace(" ", "_")
                    summary[key] = _altdata_store(db, key, _df_records(hdf), as_of)
                except Exception as e:
                    summary["13f_" + fund.split()[0].lower()] = f"err:{type(e).__name__}"
        except Exception as e:
            summary["13f"] = f"err:{type(e).__name__}"

        db.commit()
        logger.info("altdata_snapshot_daily: %s", summary)
    except Exception as e:
        logger.warning("altdata_snapshot_daily: fatal: %s", e)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()
