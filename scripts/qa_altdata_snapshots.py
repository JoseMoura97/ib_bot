#!/usr/bin/env python3
"""Persist today's alt-data QA line or verify its committed green streak."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO))

from app.db.session import SessionLocal  # noqa: E402
from app.services.altdata_qa import (  # noqa: E402
    QA_LOG_PATH,
    backfill_existing_dates,
    run_and_write_daily_qa,
    verify_green_log_streak,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-path", type=Path, default=QA_LOG_PATH)
    parser.add_argument("--backfill-existing", action="store_true")
    parser.add_argument("--verify-committed-streak", type=int, default=0, metavar="DAYS")
    parser.add_argument("--repo-root", type=Path, default=REPO)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)

    if args.verify_committed_streak:
        result = verify_green_log_streak(
            args.log_path,
            as_of_date=now.date(),
            required_days=args.verify_committed_streak,
            repo_root=args.repo_root,
            committed_only=True,
        )
        print(json.dumps({"streak": result}, indent=2, sort_keys=True))
        return 0 if result["status"] == "green" else 1

    db = SessionLocal()
    try:
        backfill = (
            backfill_existing_dates(db, generated_at_utc=now, log_path=args.log_path)
            if args.backfill_existing
            else []
        )
        payload, appended = run_and_write_daily_qa(
            db,
            now_utc=now,
            log_path=args.log_path,
        )
    finally:
        db.close()

    result = {
        "backfill": backfill,
        "daily": payload,
        "daily_appended": appended,
        "log_path": str(args.log_path),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if payload["status"] == "green" else 1


if __name__ == "__main__":
    raise SystemExit(main())
