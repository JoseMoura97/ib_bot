#!/usr/bin/env bash
# Fresh, SHA-bound acceptance for H4 ECC d5a2a432.
#
# This wrapper deliberately owns only the three failed acceptance clauses:
# the live service credential's UPDATE/DELETE denials, the --extend refusal
# path (with proof that its existing manifest is not replaced), and the
# >=30-day live chain report.  It neither changes H5 nor loosens a threshold.
set -euo pipefail

cd "$(dirname "$0")/.."

readonly CRITICAL_FIX_SHA="ff5ee6c49f007a6121a8bb5d95df750e600e3e4c"
readonly PRIVILEGE_GATE_SHA="db74a7b801c85e01e9d376fe13f6d992c10f9e57a979dd3a9b2830c084a1b406"
readonly SCRATCH_TABLE="h4_ecc_extend_probe"
readonly RECEIPT="reports/h4_ecc_d5a2a432_acceptance.json"
readonly RUN_LOG="reports/h4_ecc_d5a2a432_runner.log"

tested_sha="$(git rev-parse HEAD)"
git merge-base --is-ancestor "$CRITICAL_FIX_SHA" "$tested_sha"
test "$(sha256sum scripts/altdata_privilege_gate.py | cut -d' ' -f1)" = "$PRIVILEGE_GATE_SHA"

scratch_manifest="$(mktemp reports/.h4_ecc_manifest.XXXXXX.json)"
scratch_report="$(mktemp reports/.h4_ecc_report.XXXXXX.json)"
scratch_baseline_before=""
# --bootstrap deliberately refuses an existing file.  Reserve an unpredictable
# name, then remove that empty placeholder before the verifier creates it.
rm -f "$scratch_manifest"

cleanup() {
  docker compose exec -T db psql -U ibbot -d ibbot -v ON_ERROR_STOP=1 -c \
    "DROP TABLE IF EXISTS ${SCRATCH_TABLE}" >/dev/null 2>&1 || true
  rm -f "$scratch_manifest" "$scratch_report"
}
trap cleanup EXIT

# This is a disposable database copy, never the archive itself.  It proves the
# CLI's production --extend path refuses an already-committed rewrite before it
# can replace its baseline on disk.
docker compose exec -T db psql -U ibbot -d ibbot -v ON_ERROR_STOP=1 <<SQL
DROP TABLE IF EXISTS ${SCRATCH_TABLE};
CREATE TABLE ${SCRATCH_TABLE} AS TABLE altdata_snapshots;
GRANT SELECT ON ${SCRATCH_TABLE} TO ibbot_app;
SQL

docker compose exec -T worker python /app/scripts/verify_altdata_chain.py \
  --table "$SCRATCH_TABLE" \
  --bootstrap \
  --manifest "/app/${scratch_manifest}" \
  --report "/app/${scratch_report}" >/dev/null

scratch_baseline_before="$(sha256sum "$scratch_manifest" | cut -d' ' -f1)"
docker compose exec -T db psql -U ibbot -d ibbot -v ON_ERROR_STOP=1 -c \
  "UPDATE ${SCRATCH_TABLE} SET payload = payload || '{\"h4_ecc_tamper\":true}'::jsonb WHERE id = (SELECT id FROM ${SCRATCH_TABLE} WHERE payload IS NOT NULL ORDER BY id LIMIT 1);" >/dev/null

set +e
docker compose exec -T worker python /app/scripts/verify_altdata_chain.py \
  --table "$SCRATCH_TABLE" \
  --extend \
  --manifest "/app/${scratch_manifest}" \
  --report "/app/${scratch_report}" >/dev/null 2>&1
tamper_exit=$?
set -e
scratch_baseline_after="$(sha256sum "$scratch_manifest" | cut -d' ' -f1)"
test "$tamper_exit" -eq 1
test "$scratch_baseline_before" = "$scratch_baseline_after"

# The existing final runner performs the live service-credential gate and the
# chain verification.  Keep its full output as the auditable source for the
# literal PostgreSQL errors stored in the receipt below.
./scripts/run_h4_final_acceptance.sh 2>&1 | tee "$RUN_LOG"

python3 - "$RECEIPT" "$RUN_LOG" "$scratch_report" "$tested_sha" \
  "$CRITICAL_FIX_SHA" "$scratch_baseline_before" "$scratch_baseline_after" <<'PY'
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

receipt_path, runner_log_path, tamper_report_path, tested_sha, critical_fix_sha, before, after = map(Path, sys.argv[1:8])
# The two SHA inputs are not filesystem paths; restore their text spellings.
tested_sha = str(tested_sha)
critical_fix_sha = str(critical_fix_sha)
runner_log = runner_log_path.read_text(encoding="utf-8")
tamper = json.loads(tamper_report_path.read_text(encoding="utf-8"))
chain = json.loads(Path("reports/altdata_chain_verify.json").read_text(encoding="utf-8"))

def gate_line(label: str) -> str:
    prefix = f"[neg] {label}:"
    for line in runner_log.splitlines():
        if line.startswith(prefix):
            return line
    raise SystemExit(f"missing privilege-gate output for {label}")

raw_update = gate_line("raw-update")
raw_delete = gate_line("raw-delete")
if not all("REJECTED" in line and "ERROR:" in line for line in (raw_update, raw_delete)):
    raise SystemExit("raw UPDATE/DELETE privilege probe did not emit rejected PostgreSQL errors")
if tamper.get("error") is None or not tamper.get("tampered_days"):
    raise SystemExit("--extend tamper refusal report is missing its literal error or affected days")
if before != after:
    raise SystemExit("--extend tamper refusal replaced the committed scratch baseline")
if not (
    chain.get("total_days", 0) >= 30
    and chain.get("chained_valid_days") == chain.get("total_days")
    and chain.get("negative_test_detected") is True
):
    raise SystemExit("live chain report did not satisfy the frozen H4 threshold")

def sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

receipt = {
    "acceptance": "H4 ECC d5a2a432 fresh acceptance",
    "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    "tested_git_sha": tested_sha,
    "critical_fix_sha": critical_fix_sha,
    "source_sha256": {
        "scripts/verify_altdata_chain.py": sha256("scripts/verify_altdata_chain.py"),
        "scripts/altdata_privilege_gate.py": sha256("scripts/altdata_privilege_gate.py"),
        "scripts/run_h4_final_acceptance.sh": sha256("scripts/run_h4_final_acceptance.sh"),
        "scripts/run_h4_ecc_acceptance.sh": sha256("scripts/run_h4_ecc_acceptance.sh"),
    },
    "gates": {
        "live_privilege_boundary": {
            "status": "pass",
            "raw_update": raw_update,
            "raw_delete": raw_delete,
        },
        "extend_tamper_refusal": {
            "status": "pass",
            "command": "verify_altdata_chain.py --extend against an altered disposable copy",
            "exit_code": 1,
            "literal_error": tamper["error"],
            "tampered_days": tamper["tampered_days"],
            "manifest_sha256_before": before,
            "manifest_sha256_after": after,
            "baseline_preserved": True,
        },
        "live_chain": {
            "status": "pass",
            "total_days": chain["total_days"],
            "chained_valid_days": chain["chained_valid_days"],
            "negative_test_detected": chain["negative_test_detected"],
            "top_manifest_hash": chain["top_manifest_hash"],
            "report_sha256": sha256("reports/altdata_chain_verify.json"),
        },
    },
}
temporary = receipt_path.with_suffix(receipt_path.suffix + ".tmp")
temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
temporary.replace(receipt_path)
PY

printf '0 %s %s\n' "$(date -u +%FT%TZ)" "$tested_sha" > reports/h4_final_acceptance.success
