from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_altdata_chain.py"
spec = importlib.util.spec_from_file_location("verify_altdata_chain", SCRIPT)
chain = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = chain
spec.loader.exec_module(chain)


def row(day: str, source: str, payload: object):
    return chain.SnapshotRow(day, source, chain.sha256_json(payload), payload)


def test_chain_verifies_all_days_and_cascades_tamper():
    baseline_rows = [
        row("2026-07-13", "a", [{"v": 1}]),
        row("2026-07-13", "b", [{"v": 2}]),
        row("2026-07-14", "a", [{"v": 3}]),
        row("2026-07-15", "a", [{"v": 4}]),
    ]
    expected = chain.manifest_document(chain.build_days(baseline_rows))
    clean = chain.verify(expected, chain.build_days(baseline_rows))
    assert clean["total_days"] == 3
    assert clean["chained_valid_days"] == 3

    tampered_rows = list(baseline_rows)
    tampered_rows[2] = row("2026-07-14", "a", [{"v": "tampered"}])
    tampered = chain.verify(expected, chain.build_days(tampered_rows))
    assert tampered["invalid_days"] == ["2026-07-14", "2026-07-15"]
    assert tampered["chained_valid_days"] == 1


def test_payload_hash_is_recomputed_not_trusted_from_column():
    original = row("2026-07-13", "a", [{"v": 1}])
    expected = chain.manifest_document(chain.build_days([original]))
    rewritten = chain.SnapshotRow("2026-07-13", "a", original.content_hash, [{"v": 2}])
    result = chain.verify(expected, chain.build_days([rewritten]))
    assert result["chained_valid_days"] == 0
    assert result["days"][0]["actual_manifest_hash"] != result["days"][0]["expected_manifest_hash"]


def test_extend_refuses_when_a_committed_day_is_tampered():
    baseline_rows = [
        row("2026-07-13", "a", [{"v": 1}]),
        row("2026-07-14", "a", [{"v": 2}]),
        row("2026-07-15", "a", [{"v": 3}]),
    ]
    old_baseline = chain.manifest_document(chain.build_days(baseline_rows))

    # New day 07-16 arrives normally: extend must accept it and rewrite the baseline.
    with_new_day = baseline_rows + [row("2026-07-16", "a", [{"v": 4}])]
    extended, pre_result = chain.extend_manifest(old_baseline, chain.build_days(with_new_day))
    # The new day is legitimately absent from the old baseline (not yet chained), so
    # verify() correctly flags it -- but it is not a "tampered" day: it is not in
    # old_dates, so extend_manifest still accepts and appends it below.
    assert pre_result["invalid_days"] == ["2026-07-16"]
    assert extended["total_days"] == 4
    assert [d["as_of_date"] for d in extended["days"]] == [
        "2026-07-13",
        "2026-07-14",
        "2026-07-15",
        "2026-07-16",
    ]

    # A retroactive rewrite of an already-committed day (07-14), *plus* the new
    # day landing normally, must never be silently absorbed into a regenerated
    # baseline: extend_manifest must refuse and report exactly the tampered
    # day and its downstream successors.
    tampered_with_new_day = list(with_new_day)
    tampered_with_new_day[1] = row("2026-07-14", "a", [{"v": "tampered"}])
    try:
        chain.extend_manifest(old_baseline, chain.build_days(tampered_with_new_day))
        raise AssertionError("extend_manifest must raise ChainTamperError on a tampered committed day")
    except chain.ChainTamperError as exc:
        assert exc.tampered_days == ["2026-07-14", "2026-07-15"]
    # The would-be-tampered baseline must never have been written to disk in
    # main(); this call proves the in-memory guard is what stops it.


def test_extend_manifest_never_regenerates_baseline_before_verifying():
    # This is the exact production bug: a naive "write current rows as the
    # baseline, then verify against that same baseline" is a tautology that
    # can never detect a retroactive rewrite.  extend_manifest must always
    # compare fresh data against the manifest that was ALREADY on disk.
    baseline_rows = [row("2026-07-13", "a", [{"v": 1}])]
    old_baseline = chain.manifest_document(chain.build_days(baseline_rows))
    tampered_rows = [row("2026-07-13", "a", [{"v": "tampered"}])]
    try:
        chain.extend_manifest(old_baseline, chain.build_days(tampered_rows))
        raise AssertionError("must not silently accept a tampered day with no new days appended")
    except chain.ChainTamperError as exc:
        assert exc.tampered_days == ["2026-07-13"]


def test_psycopg_url_and_prior_negative_proof(tmp_path):
    assert chain.psycopg_url("postgresql+psycopg://user:pass@db/example") == "postgresql://user:pass@db/example"
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"negative_test_detected": True, "negative_test": {"detected": True}}))
    assert chain.prior_negative_proof(report) == {"detected": True}


def test_split_closed_days_excludes_today_and_later():
    days = [{"as_of_date": d} for d in ["2026-10-11", "2026-10-12", "2026-10-13", "2026-10-14"]]
    closed, open_days = chain.split_closed_days(days, "2026-10-13")
    assert [d["as_of_date"] for d in closed] == ["2026-10-11", "2026-10-12"]
    assert [d["as_of_date"] for d in open_days] == ["2026-10-13", "2026-10-14"]


def test_extend_never_seals_an_open_same_day_late_capture_no_longer_trips_tamper():
    """Root cause (2026-10-13): --extend sealed "today" before it closed, so a
    later same-day additive row broke its own freshly-written seal. Excluding
    the open day before calling extend_manifest means a late same-day capture
    is simply absent from the baseline -- never a tamper -- until the day
    actually closes.
    """
    today = "2026-10-14"
    baseline_rows = [row("2026-10-12", "a", [{"v": 1}])]
    old_baseline = chain.manifest_document(chain.build_days(baseline_rows))

    # First run of the day: one source landed for "today" (open, excluded).
    first_run_rows = baseline_rows + [row("2026-10-14", "a", [{"v": 2}])]
    closed_1, open_1 = chain.split_closed_days(chain.build_days(first_run_rows), today)
    extended_1, _pre = chain.extend_manifest(old_baseline, closed_1)
    assert [d["as_of_date"] for d in extended_1["days"]] == ["2026-10-12"]
    assert [d["as_of_date"] for d in open_1] == ["2026-10-14"]

    # Later the SAME UTC day: a second source lands additively for "today".
    # Because "today" was never sealed in extended_1, this is not a tamper.
    second_run_rows = first_run_rows + [row("2026-10-14", "b", [{"v": 3}])]
    closed_2, open_2 = chain.split_closed_days(chain.build_days(second_run_rows), today)
    extended_2, _pre = chain.extend_manifest(extended_1, closed_2)
    assert [d["as_of_date"] for d in extended_2["days"]] == ["2026-10-12"]
    assert len(open_2[0]["sources"]) == 2


def test_extend_still_refuses_mutation_of_a_closed_sealed_day():
    baseline_rows = [row("2026-10-12", "a", [{"v": 1}]), row("2026-10-13", "a", [{"v": 2}])]
    old_baseline = chain.manifest_document(chain.build_days(baseline_rows))

    tampered_rows = [row("2026-10-12", "a", [{"v": "tampered"}]), row("2026-10-13", "a", [{"v": 2}])]
    closed, _open = chain.split_closed_days(chain.build_days(tampered_rows), "2026-10-14")
    try:
        chain.extend_manifest(old_baseline, closed)
        raise AssertionError("mutating an already-closed sealed day must still raise ChainTamperError")
    except chain.ChainTamperError as exc:
        assert exc.tampered_days == ["2026-10-12", "2026-10-13"]


def test_reseal_day_requires_reason_and_authority():
    baseline_rows = [row("2026-10-13", "a", [{"v": 1}])]
    old_baseline = chain.manifest_document(chain.build_days(baseline_rows))
    closed = chain.build_days(baseline_rows)
    for reason, authority in [(None, "jarvis"), ("legit", None), ("", ""), (None, None)]:
        try:
            chain.reseal_day(old_baseline, closed, "2026-10-13", reason, authority)
            raise AssertionError("reseal must refuse without both --reason and --authority")
        except chain.ResealError:
            pass


def test_reseal_day_rechains_successors_and_audits():
    # 10-13 was wrongly sealed with only source "a"; 10-14 later chained on top.
    old_rows = [
        row("2026-10-12", "a", [{"v": 0}]),
        row("2026-10-13", "a", [{"v": 1}]),
        row("2026-10-14", "a", [{"v": 9}]),
    ]
    old_baseline = chain.manifest_document(chain.build_days(old_rows))

    # Live data: 10-13 additionally has source "b" (the legitimate GM restore);
    # 10-14 is unchanged.
    live_rows = old_rows + [row("2026-10-13", "b", [{"v": 2}])]
    closed = chain.build_days(live_rows)

    new_baseline, audit = chain.reseal_day(
        old_baseline, closed, "2026-10-13", reason="GM restore after outage; additive row", authority="jarvis 14/10"
    )
    assert audit["as_of_date"] == "2026-10-13"
    assert audit["changed_sources"] == ["b"]
    assert audit["rechained_successors"] == ["2026-10-14"]
    assert audit["reason"] and audit["authority"]
    assert [d["as_of_date"] for d in new_baseline["days"]] == ["2026-10-12", "2026-10-13", "2026-10-14"]
    # 10-14's manifest_hash must differ from the old one: it now chains from the
    # resealed 10-13, not the old (now-superseded) seal.
    old_1014 = next(d for d in old_baseline["days"] if d["as_of_date"] == "2026-10-14")
    new_1014 = next(d for d in new_baseline["days"] if d["as_of_date"] == "2026-10-14")
    assert new_1014["manifest_hash"] != old_1014["manifest_hash"]
    # Re-verifying the new baseline against the current live data must now pass clean.
    result = chain.verify(new_baseline, closed)
    assert result["invalid_days"] == []
    assert new_baseline["reseal_log"][-1]["as_of_date"] == "2026-10-13"


def test_reseal_day_refuses_if_prefix_was_tampered():
    old_rows = [row("2026-10-12", "a", [{"v": 0}]), row("2026-10-13", "a", [{"v": 1}])]
    old_baseline = chain.manifest_document(chain.build_days(old_rows))
    tampered_prefix = [row("2026-10-12", "a", [{"v": "tampered"}]), row("2026-10-13", "a", [{"v": 1}])]
    closed = chain.build_days(tampered_prefix)
    try:
        chain.reseal_day(old_baseline, closed, "2026-10-13", reason="x", authority="y")
        raise AssertionError("reseal must refuse when a day before it no longer verifies")
    except chain.ChainTamperError as exc:
        assert exc.tampered_days == ["2026-10-12"]
