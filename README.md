# IB Bot Runtime

This repo supports a single “blessed” runtime via Docker Compose and nginx.
The default access point is:

- `http://localhost:8080` (nginx reverse proxy)

## Quick start (docker-compose)

1) Create a `.env` from `.env.example`.
2) Start the stack:

```
docker-compose up --build
```

3) Open the UI at `http://localhost:8080`.

## Services and ports

`docker-compose.yml` runs the following services:

- `db` (PostgreSQL) on `5432`
- `redis` on `6379`
- `api` (FastAPI) on `8000`
- `worker` (Celery)
- `beat` (Celery Beat)
- `web` (Next.js) on `3000`
- `nginx` on `8080` (public entrypoint)

nginx proxies:

- `/api/*` → `api:8000`
- `/` → `web:3000`

See `infra/nginx/nginx.conf` for the exact routing.

## Paper-first workflow

Start with paper trading and prove repeated rebalance cycles before turning on live execution.

- Paper UI: `http://localhost:8080/paper`
- Live UI (safe mode by default): `http://localhost:8080/live`

Live execution requires `ENABLE_LIVE_TRADING=1` in the environment.

## Data + cache paths

The stack mounts `.cache` into the Python services:

- `./.cache` → `/app/.cache`

This stores plot data, price caches, and validation outputs.

## Logs and database

- Container logs: `docker-compose logs -f`
- Database: Postgres container `db`

## Troubleshooting

- If IB Gateway/TWS is running on your host, use:
  - `IB_HOST=host.docker.internal`
  - `IB_PORT=4001` (paper) or `IB_PORT=4002` (live), depending on your setup
- If IB is not reachable, live endpoints will return a clear error.
