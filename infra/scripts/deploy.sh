#!/bin/bash
set -e

PROJECT_DIR="/home/ibbot/ib_bot"
BRANCH="${1:-portfolios-builder-allocations-ui}"

cd "$PROJECT_DIR"

echo ">>> Pulling latest from origin/$BRANCH..."
GIT_TERMINAL_PROMPT=0 git fetch origin
git checkout "$BRANCH"
GIT_TERMINAL_PROMPT=0 git pull origin "$BRANCH"

echo ">>> Rebuilding and restarting containers..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

echo ">>> Waiting for services to start..."
sleep 10

echo ">>> Service status:"
docker compose ps

echo ">>> Health check:"
curl -sf http://localhost:8080/api/health && echo "" || echo "API not responding yet (may still be starting)"

echo ">>> Deploy complete!"
