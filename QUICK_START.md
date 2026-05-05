# IB Bot — Quick Start (Docker Stack)

**Business purpose:** Automated IB (Interactive Brokers) trading bot that replicates
Quiver Quant strategies (congressional trades, lobbying, 13F filings). FastAPI backend +
Next.js dashboard + Celery workers. Runs paper and live rebalancing on a schedule.

---

## Requirements

- Docker + Docker Compose v2
- A `.env` file in the project root (copy from `.env.example`, fill in secrets)
- IB Gateway running (for live/paper trading — see below)
- `QUIVER_API_KEY` for strategy signals (without it, only the 3 free 13F strategies work)

---

## Local / EPYC dev (shadow, no live trading)

```bash
cd ~/Desktop/cursor-projects/ib_bot

# First time — copy and fill secrets
cp .env.example .env
# Set at minimum: QUIVER_API_KEY, API_KEY (optional but recommended)

# Start everything (EPYC override avoids port conflicts with Grafana/host PG/host Redis)
COMPOSE='-f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.epyc.yml'
docker compose $COMPOSE up -d --build

# Health check
curl http://localhost:8001/health        # API direct
curl http://localhost:8090/api/health   # via nginx

# Dashboard UI
http://100.67.188.93:8090/
```

Ports on EPYC:
| Service | Host port |
|---------|-----------|
| nginx (UI + /api proxy) | 8090 |
| API (direct) | 8001 |
| DB/Redis | internal only |

---

## Production (Finland server, `213.159.68.39`)

```bash
# From local: commit + push, then:
ssh root@213.159.68.39 "cd /home/ibbot/ib_bot && \
  GIT_TERMINAL_PROMPT=0 git pull origin portfolios-builder-allocations-ui && \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build"

# Or use the deploy script:
ssh root@213.159.68.39 "/home/ibbot/deploy.sh"
```

Dashboard: `http://213.159.68.39`

---

## .env — minimum required values

```bash
# Copy the example, then fill in:
QUIVER_API_KEY=<your key from quiverquant.com>
API_KEY=<random secret for UI/API auth, or leave blank for no auth>

# IB Gateway (Finland production):
IB_HOST=172.18.0.1
IB_PORT=4003         # socat proxy → IB Gateway 4001

# Trading safety (keep false until paper is validated):
ENABLE_LIVE_TRADING=false
LIVE_DRY_RUN=true
```

All other values have sane defaults in `.env.example`.

---

## Database migrations

```bash
docker compose exec api alembic upgrade head
# (runs automatically on container startup via docker-entrypoint.sh)
```

---

## IB Gateway (for live/paper trading)

1. IB Gateway 10.37 runs on the host (not in Docker), headless via Xvfb.
2. Start it: `DISPLAY=:1 nohup /opt/ibgateway/ibgateway > /tmp/gw.log 2>&1 &`
3. Login via VNC at `:5900` with TOTP from `/opt/ibc/auto2fa.py`.
4. Set `IB_HOST=172.18.0.1`, `IB_PORT=4003` in `.env`, recreate api/worker/beat.
5. Enable API: Gateway → Configure → Settings → API Settings → port 4001.

Full details: `.cursor/rules/server-setup.mdc`

---

## Scheduled tasks (Celery Beat, UTC)

| Task | Schedule | Purpose |
|------|----------|---------|
| `refresh_plot_data_nightly` | 02:00 daily | Regenerate strategy equity curves |
| `refresh_validation_weekly` | 03:00 Sunday | Backtest all 20 strategies vs Quiver |
| `shadow_preview_daily` | 06:00 daily | Preview live rebalancing targets |
| `paper_rebalance_daily` | 15:00 daily | Auto-rebalance paper portfolios |
| `paper_snapshot_daily` | 21:30 daily | Snapshot paper P&L |

---

## Common ops

```bash
COMPOSE='-f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.epyc.yml'

# Status
docker compose $COMPOSE ps

# Logs
docker compose $COMPOSE logs -f api
docker compose $COMPOSE logs -f worker

# Force-recreate after .env change
docker compose $COMPOSE up -d --force-recreate api worker beat

# Emergency halt
echo "TRADING_HALT=true" >> .env && docker compose $COMPOSE restart api worker

# Trigger plot data refresh manually
docker exec ib_bot-api-1 curl -s -X POST 'http://localhost:8000/plot-data/refresh?force=true'

# DB shell
docker compose $COMPOSE exec db psql -U ibbot -d ibbot
```

---

## What Jibas needs to provide

- [ ] `QUIVER_API_KEY` — from quiverquant.com (required for 18/22 strategies)
- [ ] IB Gateway login — manual 2FA via VNC; `jibas.bot` (U15721390) is the main account
- [ ] `API_KEY` — any random string; set the same in `.env` and frontend `INTERNAL_API_KEY`
- [ ] `POSTGRES_PASSWORD` — change from default `ibbot` for production
- [ ] `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` — optional, for trade alerts

---

## Known gotchas

- IB Gateway **rejects non-localhost connections** from Docker. Use socat proxy on port 4003.
- Do **NOT** set `SecondFactorDevice` in IBC config — causes lockout from rapid failed 2FA.
- After ~5 failed 2FA attempts, IB locks the account for ~24h.
- EPYC shadow env uses `IB_PORT=4999` (intentionally unreachable) — IB connection errors in logs are expected.
- `.cache/plot_data.json` must be seeded locally and SCP'd to server; on-server generation fails for delisted tickers.

Full ops reference: `docs/RUNBOOK.md` and `.cursor/rules/server-setup.mdc`
