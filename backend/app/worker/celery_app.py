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
    },
)

# Import tasks so Celery can discover them.
from app.worker import tasks  # noqa: E402,F401
