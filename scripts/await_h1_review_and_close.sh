#!/usr/bin/env bash
# Bounded durable continuation for the H1 independent-review gate.
set -euo pipefail

review_id='c5a4a697-6b22-451f-a819-f6502fffd207'
plan_slug='ib_bot-altdata-hardening'
phase_id='h1_offsite_restore_proof'

for _attempt in $(seq 1 80); do
    verdict="$(psql conductor -Atqc "SELECT COALESCE(verdict, '') FROM ecc_phase_code_reviews WHERE id = '${review_id}'")"

    case "${verdict}" in
        pass)
            conductor plan set-phase "${plan_slug}" "${phase_id}" done --by jarvis --note \
                "Independent ECC review ${review_id} passed. Live H1 evidence remains: ib-altdata-backup.timer enabled with a scheduled next run; docs/altdata_restore_drill.md commit 8e81ddd40da311912f3808525932fb9adc394f54 records 328 restored/live rows and diff_rows=0. The 328 floor preserves the documented 2026-07-13 9/11-source gap without retroactive backfill."
            status="$(psql conductor -Atqc "SELECT value->>'status' FROM project_plans p CROSS JOIN LATERAL jsonb_array_elements(p.phases::jsonb) value WHERE p.id = '04bf8af8-6614-4f12-9d57-772f7af2b67d' AND value->>'id' = '${phase_id}'")"
            test "${status}" = 'done'
            exit 0
            ;;
        fail)
            psql conductor -Atqc "SELECT COALESCE(verdict_notes, 'review failed without notes') FROM ecc_phase_code_reviews WHERE id = '${review_id}'" >&2
            exit 42
            ;;
        '')
            sleep 15
            ;;
        *)
            printf 'unexpected review verdict: %s\n' "${verdict}" >&2
            exit 44
            ;;
    esac
done

printf 'review %s did not reach a verdict within 20 minutes\n' "${review_id}" >&2
exit 43
