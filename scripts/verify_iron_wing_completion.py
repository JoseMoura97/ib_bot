#!/usr/bin/env python3
"""Fail-closed verifier for the 2026-07-13 Iron Wing completion package."""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "reports" / "iron_wing_full_analysis_2026-07-13"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    metrics = load(RUN / "reconciliation_metrics.json")
    operational = load(RUN / "operational_evidence.json")
    inventory = load(RUN / "source_coverage_inventory.json")
    manifest = load(ROOT / "reports" / "completion_manifest.json")
    report = (ROOT / "reports" / "iron_wing_full_analysis_2026-07-13.md").read_text(encoding="utf-8")
    checks: dict[str, bool] = {}

    def check(name: str, condition) -> None:
        checks[name] = bool(condition)

    required_artifacts = [ROOT / relative for relative in manifest["artifacts"]]
    check("artifacts_exist_nonempty", all(path.exists() and path.stat().st_size > 0 for path in required_artifacts))
    check("report_has_verdict", all(term in report for term in ("não pagar os $80/mês", "não colocar a estratégia live", "0/1296")))
    check("datasets_complete", metrics["inputs"]["intraday_rows"] == 3264 and metrics["inputs"]["eod_rows"] == 3692)
    check("offline_reconciliation_safe", all(metrics["safety"][key] == 0 for key in ("ib_requests", "orders_placed", "subscriptions_purchased")))

    timing = metrics["historical_timing_audit"]
    check("timing_audit_versioned", timing["evidence_version"] == "iron-wing-timing-audit-v1-2026-07-13")
    check("timing_values_recomputed", timing["all_expected_values_verified"] is True)
    check("timing_source_counts", timing["source_counts"] == {"all": 3264, "amc": 1514, "bmo": 1750, "heldout_bmo": 1296})
    check("bmo_repair_data_absent", timing["correct_prior_day_theta_raw_availability"]["available"] == 0
          and timing["correct_prior_day_theta_raw_availability"]["required"] == 1296)
    expected = timing["expected_rounded_audit_values"]
    check("amc_commission_010", expected["valid_amc_heldout"]["slip_0.10_commission_5_20"]
          == {"n": 531, "mean_return_pct": 15.4, "profit_factor": 1.801})
    check("amc_commission_025", expected["valid_amc_heldout"]["slip_0.25_commission_5_20"]
          == {"n": 531, "mean_return_pct": 10.01, "profit_factor": 1.475})
    check("bmo_bug_drags_not_creates", "drag" in timing["bug"]["effect"].lower())

    collector = operational["collector_validation"]
    check("initial_population_9_of_9", collector["initial_population_run"]["successful_sources"] == 9
          and collector["initial_population_run"]["failed_sources"] == 0)
    for label in ("post_patch_validation", "idempotent_cached_rerun"):
        audit = collector[label]
        check(f"{label}_9_of_9", audit["expected_sources"] == audit["accounted_sources"] == audit["successful_sources"] == 9)
        check(f"{label}_mandatory_green", audit["mandatory_failed_sources"] == 0 and audit["overall_status"] == "ok")
        check(f"{label}_safe", audit["ib_requests"] == audit["orders_placed"] == audit["subscriptions_purchased"] == 0)
    rerun = collector["idempotent_cached_rerun"]
    check("idempotent_all_exists", all(result["status"] == "exists" for result in rerun["results"]))
    check("database_has_9_vintages", collector["database_snapshot_rows"] == 9)
    check("sole_external_schedule", operational["daily_coverage_schedule"]["sole_schedule_verified"] is True)
    check("forward_timers_active", operational["forward_systemd_timers"]["options_cache_active"] is True
          and operational["forward_systemd_timers"]["paper_ironfly_active"] is True)
    check("operational_safety_zero", all(value == 0 for value in operational["safety"].values()))

    notes = collector["post_patch_validation"]["source_notes"]
    check("quiver_exclusion_explicit", "excluded" in notes["quiver_congress_trades"])
    check("house_index_limitation_explicit", "metadata" in notes["house_financial_disclosure_index"])
    excluded = {item["source"]: item["reason"] for item in inventory["explicitly_excluded"]}
    quiver_reason = excluded["Quiver bulk Congress endpoint"]
    check("inventory_quiver_not_fake_replacement", "deliberately excluded" in quiver_reason
          and "equivalent" in quiver_reason)

    forward = operational["forward_validation"]
    check("operational_evidence_fresh", datetime.fromisoformat(
        operational["captured_at_utc"].replace("Z", "+00:00")
    ).date().isoformat() == "2026-07-13")
    check("trading_commit", forward["trading_commit"].startswith("b98e15041"))
    check("dolt_safe_sync", forward["dolt_calendar_sync"]["mode"] == "fetch_then_ff_only"
          and forward["dolt_calendar_sync"]["status"] in {"synced", "up_to_date", "recent_sync"})
    check("paper_audit_safe", forward["paper_ironfly"]["logged_this_run"] >= 3
          and forward["paper_ironfly"]["ib_requests"] == forward["paper_ironfly"]["orders_placed"] == 0)

    ledger = forward["paper_ledger"]
    events = ledger["events"]
    check("ledger_has_3_events", ledger["rows"] >= 3 and len(events) >= 3)
    baseline_keys = {("GIS", "2026-07-01"), ("PEP", "2026-07-09"), ("DAL", "2026-07-10")}
    baseline = [event for event in events if (event["symbol"], event["exit_ts_utc"][:10]) in baseline_keys]
    check("baseline_ledger_events_present", len(baseline) == 3
          and {(event["symbol"], event["exit_ts_utc"][:10]) for event in baseline} == baseline_keys)
    event_times = [event[key] for event in baseline for key in ("entry_ts_utc", "exit_ts_utc")]
    near_close = []
    for value in event_times:
        local = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York"))
        near_close.append(abs((local.hour * 60 + local.minute + local.second / 60) - (15 * 60 + 45)) <= 2)
    check("ledger_timestamps_near_1545_et", all(near_close))
    check("ledger_commission_0_052", ledger["commission_quote_all_0_052"] is True)
    check("ledger_touch_le_mid", ledger["touch_le_mid_all"] is True)
    mid_mean = sum(event["ret_mid"] for event in baseline) / len(baseline) if baseline else math.nan
    touch_mean = sum(event["ret_touch"] for event in baseline) / len(baseline) if baseline else math.nan
    check("baseline_ledger_mid_mean", math.isclose(mid_mean, -0.0458171463, abs_tol=1e-9))
    check("baseline_ledger_touch_mean", math.isclose(touch_mean, -0.2647468949, abs_tol=1e-9))
    check("test_evidence", manifest["tests"]["ib_bot_equity_coverage"]["passed"] == 10
          and manifest["tests"]["trading_forward"]["passed"] == 18)
    check("manifest_safety", all(value == 0 for value in manifest["safety"].values()))

    failed = sorted(name for name, ok in checks.items() if not ok)
    payload = {"checks": len(checks), "passed": len(checks) - len(failed), "failed": failed, "ok": not failed}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
