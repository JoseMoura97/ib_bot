from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings


celery_app = Celery(
    "ib_bot_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        # Nightly refresh of plot_data.json (skips if recent unless forced)
        "refresh_plot_data_nightly": {
            "task": "refresh_plot_data_task",
            "schedule": crontab(hour=2, minute=0),
            "kwargs": {"force": False, "max_age_hours": 24},
        },
        # Weekly refresh of validation metrics (can be expensive)
        "refresh_validation_weekly": {
            "task": "refresh_validation_results_task",
            "schedule": crontab(day_of_week="sun", hour=3, minute=0),
            "kwargs": {"force": False, "max_age_hours": 24 * 7},
        },
        "shadow_preview_daily": {
            "task": "shadow_preview_task",
            "schedule": crontab(hour=6, minute=0),
        },
        "paper_rebalance_daily": {
            "task": "paper_rebalance_daily_task",
            "schedule": crontab(hour=15, minute=0),  # 15:00 UTC = ~10:00 AM ET
        },
        # Unattended LIVE auto-rebalance — self-skips unless LIVE_AUTO_REBALANCE
        # is armed, the market is open, and an allocation's cadence is due.
        "live_rebalance_hourly": {
            "task": "live_rebalance_scheduled_task",
            "schedule": crontab(minute=0, hour="14-21"),  # hourly during US market hours
        },
        "paper_snapshot_daily": {
            "task": "paper_snapshot_daily_task",
            "schedule": crontab(hour=21, minute=30),  # 21:30 UTC = ~4:30 PM ET
        },
        # Daily point-in-time vintage of every free alt-data source (the compounding archive).
        "altdata_snapshot_daily": {
            "task": "altdata_snapshot_daily_task",
            "schedule": crontab(hour=5, minute=0),  # 05:00 UTC, before market open
        },
        # Phase 2: Reconcile stuck IN_PROGRESS execution rows every 5 minutes
        "reconcile_stuck_executions": {
            "task": "reconcile_stuck_executions_task",
            "schedule": 300,  # every 5 minutes
        },
        # Reconcile orphaned RUNNING rows in `runs` (worker crash / SIGKILL)
        "reconcile_stuck_runs": {
            "task": "reconcile_stuck_runs_task",
            "schedule": 600,  # every 10 minutes
        },
    },
)

# Import tasks so Celery can discover them.
from app.worker import tasks  # noqa: E402,F401
