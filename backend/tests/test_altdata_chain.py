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
