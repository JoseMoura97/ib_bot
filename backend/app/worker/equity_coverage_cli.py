"""Synchronous entry point for systemd and validation runs."""
from __future__ import annotations

import json

from app.db.session import SessionLocal
from app.services.equity_coverage import capture_all


def main() -> int:
    db = SessionLocal()
    try:
        audit = capture_all(db)
    finally:
        db.close()
    print(json.dumps({
        "successful_sources": audit["successful_sources"],
        "failed_sources": audit["failed_sources"],
        "mandatory_failed_sources": audit["mandatory_failed_sources"],
        "optional_failed_sources": audit["optional_failed_sources"],
        "overall_status": audit["overall_status"],
        "as_of_date": audit["as_of_date"],
    }, sort_keys=True))
    # A typed optional outage (for example SEC 403) remains visible in the
    # audit but must not make an otherwise complete daily capture red.
    return 0 if audit["successful_sources"] and not audit["mandatory_failed_sources"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
