#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

test "$(sha256sum scripts/altdata_privilege_gate.py | cut -d' ' -f1)" = \
  db74a7b801c85e01e9d376fe13f6d992c10f9e57a979dd3a9b2830c084a1b406

docker compose build api worker beat
# The application containers deliberately use ibbot_app.  Alembic is the
# exceptional migration/admin path and must use the bootstrap role; otherwise
# the application credential cannot create roles or alter ownership.
docker compose run --rm --no-deps \
  -e DATABASE_URL=postgresql+psycopg://ibbot:ibbot@db:5432/ibbot \
  api alembic -c backend/alembic.ini upgrade head

# Recreate the three application processes one at a time after the migration.
docker compose up -d --no-deps api
sleep 5
docker compose up -d --no-deps worker
sleep 5
docker compose up -d --no-deps beat
sleep 5

python3 scripts/altdata_privilege_gate.py
docker compose exec -T worker python /app/scripts/verify_altdata_chain.py \
  --write-manifest --negative-test \
  --manifest /app/reports/altdata_chain_manifest.json \
  --report /app/reports/altdata_chain_verify.json
jq -e '.total_days==30 and .chained_valid_days==.total_days and .negative_test_detected==true' \
  reports/altdata_chain_verify.json >/dev/null

printf '0 %s\n' "$(date -u +%FT%TZ)" > reports/h4_final_acceptance.success
