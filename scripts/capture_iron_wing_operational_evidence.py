#!/usr/bin/env python3
"""Capture concise, machine-readable service/schedule/database evidence."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def command(args: list[str], cwd: Path = ROOT, timeout: int = 60) -> dict:
    process = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return {
        "command": args,
        "exit_code": process.returncode,
        "stdout": process.stdout[-10_000:],
        "stderr": process.stderr[-4_000:],
    }


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--collector-initial", type=Path, required=True)
    parser.add_argument("--collector-run-1", type=Path, required=True)
    parser.add_argument("--collector-run-2", type=Path, required=True)
    args = parser.parse_args()

    trading = Path("/home/servidor/Desktop/cursor-projects/trading")
    duplicate_units = [
        str(path.relative_to(ROOT))
        for path in (ROOT / "infra" / "equity-coverage.service", ROOT / "infra" / "equity-coverage.timer")
        if path.exists()
    ]
    duplicate_timer = command(["systemctl", "is-enabled", "equity-coverage.timer"])
    timers = command([
        "systemctl", "show", "options-cache.timer", "paper-ironfly.timer",
        "-p", "Id", "-p", "ActiveState", "-p", "UnitFileState",
        "-p", "NextElapseUSecRealtime", "--no-pager",
    ])
    celery = command([
        "docker", "compose", "exec", "-T", "worker", "celery", "-A",
        "app.worker.celery_app", "inspect", "registered", "--timeout", "10",
    ], timeout=30)
    celery_schedule = command([
        "docker", "compose", "exec", "-T", "worker", "python", "-c",
        "from app.worker.celery_app import celery_app; "
        "s=[v for v in celery_app.conf.beat_schedule.values() "
        "if v.get('task')=='altdata_snapshot_daily_task']; "
        "print(len(s), sorted(s[0]['schedule'].hour), sorted(s[0]['schedule'].minute))",
    ])
    containers = command(["docker", "compose", "ps", "--format", "json"])
    database = command([
        "docker", "compose", "exec", "-T", "db", "psql", "-U", "ibbot", "-d", "ibbot",
        "-At", "-F", "|", "-c",
        "SELECT source,as_of_date,n_rows FROM altdata_snapshots ORDER BY source;",
    ])
    timer_states = {}
    for block in timers["stdout"].strip().split("\n\n"):
        fields = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        if fields.get("Id"):
            timer_states[fields["Id"]] = fields
    collector_initial = load(args.collector_initial)
    collector_1, collector_2 = load(args.collector_run_1), load(args.collector_run_2)
    paper_audit = load(trading / "data/options_cache/paper_ironfly_last_run.json")
    earnings_audit = load(trading / "data/options_cache/earnings_calendar_yahoo_last_run.json")
    dolt_audit = load(trading / "data/options_cache/earnings_calendar_dolt_sync_last_run.json")
    trading_commit = command(["git", "rev-parse", "HEAD"], cwd=trading)
    ledger_probe = command([
        str(trading / ".venv/bin/python"), "-c",
        "import json,pandas as pd; "
        "d=pd.read_parquet('data/options_cache/paper_ironfly_ledger.parquet'); "
        "pf=lambda s: float(s[s>0].sum()/-s[s<0].sum()) if (s<0).any() else None; "
        "events=[{'symbol':r.symbol,'entry_ts_utc':str(r.entry_ts_utc),"
        "'exit_ts_utc':str(r.exit_ts_utc),'commission_quote':float(r.commission_quote),"
        "'ret_mid':float(r.ret_mid),'ret_touch':float(r.ret_touch)} for r in d.itertuples()]; "
        "near=lambda x: (lambda t: t.hour==15 and abs(t.minute-45)<=1)(pd.Timestamp(x).tz_convert('America/New_York')); "
        "print(json.dumps({'rows':len(d),'events':events,"
        "'all_near_1545_et':all(near(x) for x in list(d.entry_ts_utc)+list(d.exit_ts_utc)),"
        "'touch_le_mid_all':bool((d.ret_touch<=d.ret_mid).all()),"
        "'commission_quote_all_0_052':bool((d.commission_quote.sub(.052).abs()<1e-12).all()),"
        "'mid':{'mean':float(d.ret_mid.mean()),'profit_factor':pf(d.ret_mid),'win_rate':float((d.ret_mid>0).mean())},"
        "'touch':{'mean':float(d.ret_touch.mean()),'profit_factor':pf(d.ret_touch),'win_rate':float((d.ret_touch>0).mean())}}))",
    ], cwd=trading)
    ledger_evidence = json.loads(ledger_probe["stdout"]) if ledger_probe["exit_code"] == 0 else {
        "error": ledger_probe["stderr"], "rows": 0
    }
    payload = {
        "schema_version": 1,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "daily_coverage_schedule": {
            "primary": "Celery beat altdata_snapshot_daily at 06:00 UTC",
            "redundant_systemd_units_in_repo": duplicate_units,
            "redundant_systemd_timer_enabled": duplicate_timer["exit_code"] == 0,
            "celery_registered_exit_code": celery["exit_code"],
            "celery_task_registered": "altdata_snapshot_daily_task" in celery["stdout"],
            "celery_schedule_probe": celery_schedule,
            "sole_schedule_verified": (
                not duplicate_units
                and duplicate_timer["exit_code"] != 0
                and celery_schedule["exit_code"] == 0
                and celery_schedule["stdout"].strip() == "1 [6] [0]"
            ),
        },
        "forward_systemd_timers": {
            "command_exit_code": timers["exit_code"],
            "raw": timers["stdout"],
            "states": timer_states,
            "options_cache_active": timer_states.get("options-cache.timer", {}).get("ActiveState") == "active",
            "paper_ironfly_active": timer_states.get("paper-ironfly.timer", {}).get("ActiveState") == "active",
        },
        "runtime": {"containers": containers, "database": database},
        "collector_validation": {
            "initial_population_run": collector_initial,
            "post_patch_validation": collector_1,
            "idempotent_cached_rerun": collector_2,
            "database_snapshot_rows": len([line for line in database["stdout"].splitlines() if line.strip()]),
        },
        "forward_validation": {
            "trading_commit": trading_commit["stdout"].strip(),
            "paper_ironfly": paper_audit,
            "earnings_calendar": earnings_audit,
            "dolt_calendar_sync": dolt_audit,
            "paper_ledger": ledger_evidence,
        },
        "safety": {
            "collector_orders_placed": max(
                collector_initial["orders_placed"], collector_1["orders_placed"], collector_2["orders_placed"]
            ),
            "collector_ib_requests": max(
                collector_initial["ib_requests"], collector_1["ib_requests"], collector_2["ib_requests"]
            ),
            "collector_subscriptions_purchased": max(
                collector_initial["subscriptions_purchased"], collector_1["subscriptions_purchased"],
                collector_2["subscriptions_purchased"]
            ),
            "forward_orders_placed": paper_audit["orders_placed"],
            "forward_ib_requests": paper_audit["ib_requests"],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    required_ok = (
        timers["exit_code"] == 0
        and celery["exit_code"] == 0 and payload["daily_coverage_schedule"]["celery_task_registered"]
        and payload["daily_coverage_schedule"]["sole_schedule_verified"]
        and collector_1["accounted_sources"] == collector_1["expected_sources"] == 9
        and collector_2["accounted_sources"] == collector_2["expected_sources"] == 9
        and collector_1["mandatory_failed_sources"] == collector_2["mandatory_failed_sources"] == 0
        and dolt_audit["mode"] == "fetch_then_ff_only"
        and dolt_audit["status"] in {"synced", "up_to_date", "recent_sync"}
        and trading_commit["stdout"].strip().startswith("b98e15041")
        and ledger_evidence["rows"] >= 3
        and ledger_evidence["all_near_1545_et"]
        and ledger_evidence["touch_le_mid_all"]
        and ledger_evidence["commission_quote_all_0_052"]
    )
    print(json.dumps({"output": str(args.output), "required_ok": required_ok}, sort_keys=True))
    return 0 if required_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
