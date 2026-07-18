#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bundle_commit="561b7e8"
bundle_path="reports/f2_backtest_alerta_evidence_20260718.md"
plan_id="e36e04ec-de9c-438f-b0e5-434dfa391154"
phase_id="f2_backtest_fix_alerta"

# The immutable bundle is the oracle.  The /var/tmp remediation files are
# intentionally not read: they are wake/coordination state, not acceptance.
git -C "$repo_dir" cat-file -e "${bundle_commit}^{commit}"
git -C "$repo_dir" show "${bundle_commit}:${bundle_path}" \
  | grep -Fq "Result=success  ExecMainStatus=0"
git -C "$repo_dir" show "${bundle_commit}:${bundle_path}" \
  | grep -Fq "Generated plot data for 56/56 strategies"
git -C "$repo_dir" show "${bundle_commit}:${bundle_path}" \
  | grep -Fq "id 74931"
git -C "$repo_dir" show "${bundle_commit}:${bundle_path}" \
  | grep -Fq "id 70288"
git -C "$repo_dir" show "${bundle_commit}:${bundle_path}" \
  | grep -Fq "id 70265"
git -C "$repo_dir" show "${bundle_commit}:${bundle_path}" \
  | grep -Fq "Correct oracle uses exec_main_status"
git -C "$repo_dir" show "${bundle_commit}:${bundle_path}" \
  | grep -Fq "Columns = id,agent_id,project_id,kind,payload,created_at"

phase_state="$({
  psql -X -v ON_ERROR_STOP=1 -d conductor -At -F '|' \
    -v plan_id="$plan_id" -v phase_id="$phase_id" <<'SQL'
WITH target AS (
  SELECT p.metadata, ph
  FROM project_plans p
  CROSS JOIN LATERAL jsonb_array_elements(p.phases) AS ph
  WHERE p.id = :'plan_id'::uuid
    AND ph->>'id' = :'phase_id'
)
SELECT
  ph->>'status',
  (ph->>'acceptance' = metadata->'acceptance_lock'->:'phase_id'->>'text')::int,
  jsonb_array_length(metadata->'acceptance_lock'->:'phase_id'->'criteria'),
  (metadata->'acceptance_lock'->:'phase_id'->>'text' LIKE '%561b7e8%')::int,
  (metadata->'acceptance_lock'->:'phase_id'->>'text' LIKE '%must never reopen or fail f2%')::int,
  (metadata->'acceptance_lock'->:'phase_id'->'criteria'->>1 LIKE '%payload.exec_main_status%')::int,
  (metadata->'acceptance_lock'->:'phase_id'->'criteria'->>2 LIKE '%id,agent_id,project_id,kind,payload,created_at%')::int,
  (ph->>'notes' LIKE '%PERMANENT ORACLE PRECEDENCE%')::int
FROM target;
SQL
})"

IFS='|' read -r phase_status lock_matches criteria_count has_bundle \
  forbids_sentinel_reopen has_correct_receipt_key has_schema note_canonical \
  <<<"$phase_state"

test "$phase_status" = "done"
test "$lock_matches" = "1"
test "$criteria_count" = "3"
test "$has_bundle" = "1"
test "$forbids_sentinel_reopen" = "1"
test "$has_correct_receipt_key" = "1"
test "$has_schema" = "1"
test "$note_canonical" = "1"

verifier_state="$({
  psql -X -v ON_ERROR_STOP=1 -d conductor -At -F '|' \
    -v plan_id="$plan_id" -v phase_id="$phase_id" <<'SQL'
SELECT
  payload->>'accepted',
  jsonb_array_length(payload->'criteria'),
  payload->>'provenance',
  payload->>'oracle_precedence'
FROM events
WHERE kind = 'phase_verified'
  AND payload->>'plan_id' = :'plan_id'
  AND payload->>'phase_id' = :'phase_id'
  AND payload->>'oracle_precedence' = 'committed_bundle_over_ephemeral_sentinel'
ORDER BY id DESC
LIMIT 1;
SQL
})"

IFS='|' read -r verifier_accepted verifier_criteria verifier_provenance \
  verifier_precedence <<<"$verifier_state"

test "$verifier_accepted" = "true"
test "$verifier_criteria" = "3"
test "$verifier_provenance" = "oracle:cmd"
test "$verifier_precedence" = "committed_bundle_over_ephemeral_sentinel"

echo "PASS: f2 is done; 561b7e8 is canonical; 3/3 frozen oracle checks are green"
