#!/usr/bin/env bash
# Weekly SAFE Docker cleanup for the EPYC host (ib_bot audit 2026-10-12, finding #4).
#
# Removes ONLY:
#   - dangling images (untagged, no container reference) older than PRUNE_UNTIL
#   - unused build cache older than PRUNE_UNTIL
# Never: volumes, networks, containers, tagged images, `-a`/`system prune`.
# Docker itself refuses to remove any image referenced by a container
# (running or stopped). Tagged-but-unused images (e.g. the content-pinned
# altdata_qa worker image) are deliberately kept: `image prune -a` would
# delete them.
#
# Usage: docker_prune_weekly.sh [--dry-run]
set -euo pipefail

until_filter="${PRUNE_UNTIL:-720h}"
dry_run=0
[[ "${1:-}" == "--dry-run" ]] && dry_run=1

echo "docker-prune: start $(date -u +%Y-%m-%dT%H:%M:%SZ) until=${until_filter} dry_run=${dry_run}"
docker system df

echo "docker-prune: dangling image candidates (until=${until_filter}):"
docker images --filter dangling=true --filter "until=${until_filter}" \
  --format '  {{.ID}} {{.CreatedSince}} {{.Size}}' || true

if (( dry_run )); then
  echo "docker-prune: dry run, nothing removed"
  exit 0
fi

docker image prune -f --filter "until=${until_filter}"
docker builder prune -f --filter "until=${until_filter}"

docker system df
echo "docker-prune: done $(date -u +%Y-%m-%dT%H:%M:%SZ)"
