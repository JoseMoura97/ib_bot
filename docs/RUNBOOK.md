# Production Runbook

Server: `213.159.68.39` (SSH: `ssh root@213.159.68.39`)
Project: `/home/ibbot/ib_bot`

## Startup

```bash
cd /home/ibbot/ib_bot
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Verify all containers are running:
```bash
docker compose ps
```

Expected services: `db`, `redis`, `api`, `worker`, `beat`, `web`, `nginx`

## Health Checks

| Check | Command |
|-------|---------|
| API health | `curl http://localhost:8000/api/health` |
| Web frontend | `curl -I http://localhost:3000` |
| Database | `docker compose exec db pg_isready -U ibbot` |
| Redis | `docker compose exec redis redis-cli ping` |
| Worker | `docker compose logs --tail=5 worker` |
| Beat | `docker compose logs --tail=5 beat` |

## Monitoring

### Logs
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f beat

# Last 100 lines
docker compose logs --tail=100 api
```

### Key Metrics to Watch
- API response times (check nginx logs)
- Celery task completion (worker logs)
- Database connections (pg_stat_activity)
- Redis memory usage

### Scheduled Tasks (Celery Beat)
| Task | Schedule (UTC) | Purpose |
|------|---------------|---------|
| refresh_plot_data_nightly | 02:00 daily | Refresh strategy equity curves |
| refresh_validation_weekly | 03:00 Sunday | Refresh validation metrics |
| shadow_preview_daily | 06:00 daily | Preview live targets vs holdings |
| paper_rebalance_daily | 15:00 daily (~10am ET) | Auto-rebalance paper accounts |
| paper_snapshot_daily | 21:30 daily (~4:30pm ET) | Snapshot paper P&L |

## Deployment

```bash
# From local machine:
git push origin portfolios-builder-allocations-ui

# On server (or via SSH):
cd /home/ibbot/ib_bot
git pull origin portfolios-builder-allocations-ui
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

### Database Migrations
```bash
docker compose exec api alembic upgrade head
```

## Troubleshooting

### Container won't start
```bash
docker compose logs <service>     # Check for errors
docker compose restart <service>  # Try restart
docker compose up -d --build <service>  # Rebuild
```

### Database connection errors
```bash
docker compose exec db psql -U ibbot -d ibbot -c "SELECT 1"
docker compose restart db
# Wait 10s, then restart api and worker
docker compose restart api worker
```

### Celery tasks stuck
```bash
# Check worker status
docker compose logs --tail=50 worker

# Flush Redis task queue (CAUTION: drops pending tasks)
docker compose exec redis redis-cli FLUSHDB

# Restart worker
docker compose restart worker beat
```

### Out of disk space
```bash
# Check space
df -h

# Clean Docker
docker system prune -f
docker volume prune -f

# Clean old backups
ls -la /home/ibbot/ib_bot/.cache/backups/
```

### API returns 500
```bash
docker compose logs --tail=100 api | grep -i error
docker compose restart api
```

## Rollback

```bash
# Find previous commit
git log --oneline -10

# Revert to specific commit
git checkout <commit-hash>
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# To undo a migration (if needed)
docker compose exec api alembic downgrade -1
```

## Emergency: Kill-Switch

### Via API
```bash
curl -X POST http://localhost:8000/api/live/halt
```

### Via environment
```bash
cd /home/ibbot/ib_bot
echo "TRADING_HALT=true" >> .env
docker compose restart api worker
```

### Verify halt is active
```bash
curl http://localhost:8000/api/live/status
# Should show: {"halted": true, ...}
```

### Resume trading
```bash
curl -X POST http://localhost:8000/api/live/resume
# Or edit .env: TRADING_HALT=false, then restart
```

## Backup

### Database
```bash
docker compose exec db pg_dump -U ibbot ibbot > /home/ibbot/backups/db_$(date +%Y%m%d).sql
```

### Full project
```bash
tar czf /home/ibbot/backups/ib_bot_$(date +%Y%m%d).tar.gz \
  --exclude='.cache/ib_prices' \
  /home/ibbot/ib_bot/.env \
  /home/ibbot/ib_bot/.cache/plot_data.json
```
