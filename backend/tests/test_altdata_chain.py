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
    assert result["days"][0]["source_hashes_ok"] is False


def test_psycopg_url_and_prior_negative_proof(tmp_path):
    assert chain.psycopg_url("postgresql+psycopg://user:pass@db/example") == "postgresql://user:pass@db/example"
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"negative_test_detected": True, "negative_test": {"detected": True}}))
    assert chain.prior_negative_proof(report) == {"detected": True}
