## Cursor Cloud specific instructions

### Stack overview

IB Bot is an Interactive Brokers algorithmic trading platform with:
- **Backend**: Python 3.12 / FastAPI (`backend/`) — API on port 8000
- **Frontend**: Next.js 15 / React 18 / TypeScript / Tailwind CSS 4 (`frontend/`) — dashboard on port 3000
- **Workers**: Celery + Redis for async tasks (backtests, plot data generation)
- **Database**: PostgreSQL 16
- **Proxy**: nginx reverse-proxies `/api/*` → API and `/*` → Next.js on port 8080

All services run via `docker compose` from the repo root. See `docker-compose.yml` for the full service graph.

### Running the stack

```
sudo dockerd &>/tmp/dockerd.log &   # if Docker daemon is not already running
sudo docker compose up -d db redis api web nginx
```

**Gotcha — Alembic migration column length**: On a fresh database the `alembic_version` table is created with `VARCHAR(32)`, but migration revision IDs (e.g. `0008_paper_snapshots_rebalance_logs`) exceed 32 chars. Before starting the API for the first time, pre-create the table:

```sql
-- Run inside the db container:
sudo docker compose exec db psql -U ibbot -d ibbot \
  -c "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(128) NOT NULL, CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num));"
```

Then start/restart the API: `sudo docker compose up -d api`

### Running tests

- **Backend (pytest)**: `PYTHONPATH=/workspace:/workspace/backend python3 -m pytest backend/tests/ -q --ignore=backend/tests/test_plot_data_cache.py`
  - `test_plot_data_cache.py` imports a missing module (`generate_plot_data_from_cache`) — skip it.
  - Some e2e tests (`test_e2e_full_cycle.py`) and `test_api_plot_data_fallback.py` have pre-existing failures.
- **Frontend lint**: `cd frontend && npx next lint` (warnings only, no errors)

### Key API endpoints for verification

- `GET /health` — `{"ok": true}`
- `GET /strategies/catalog` — lists all 34 strategies
- `POST /portfolios` — create a portfolio
- `GET /portfolios` — list portfolios

### Notes

- The backend defaults to SQLite (`dev.db`) when `DATABASE_URL` is not set, which is convenient for local pytest runs without Docker.
- The `.cache/` directory is volume-mounted into containers for price data caching. Create it with `mkdir -p .cache` before starting the stack.
- Worker and Beat services are optional for basic dashboard usage; they're needed for background backtest execution and scheduled tasks.
- IB Gateway integration requires a live connection and is not needed for dev/testing of the dashboard.
