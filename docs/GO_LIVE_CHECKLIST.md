# Go-Live Checklist

## Pre-Deployment

- [ ] All code committed and pushed to `portfolios-builder-allocations-ui`
- [ ] `.env` on server has all required variables:
  - `DATABASE_URL` (PostgreSQL)
  - `REDIS_URL`
  - `QUIVER_API_KEY` (if using Quiver strategies)
  - `ENABLE_LIVE_TRADING=false` (until validated)
  - `TRADING_HALT=false`
  - `LIVE_DRY_RUN=true` (start in dry-run)
  - `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` (for alerts)
- [ ] Database migrations are up to date: `alembic upgrade head`
- [ ] `.cache/plot_data.json` exists with recent data
- [ ] No secrets committed to git

## Post-Deployment

- [ ] All Docker containers running: `docker compose ps`
  - [ ] db (PostgreSQL)
  - [ ] redis
  - [ ] api (FastAPI)
  - [ ] worker (Celery)
  - [ ] beat (Celery Beat)
  - [ ] web (Next.js)
  - [ ] nginx
- [ ] API responds: `curl http://localhost:8000/api/health`
- [ ] Frontend loads: open `http://213.159.68.39` in browser
- [ ] Strategy catalog page shows strategies
- [ ] Dashboard loads with real chart data

## Paper Trading Validation

- [ ] Create a paper account with $100,000
- [ ] Create a portfolio with your chosen strategies and weights
- [ ] Run the portfolio optimizer (Portfolios page > Weight Optimizer)
- [ ] Create an allocation (Allocations page) linking account to portfolio
- [ ] Run a paper rebalance preview - verify orders look correct
- [ ] Execute the paper rebalance
- [ ] Verify positions match expected allocations
- [ ] Wait for daily snapshot (4:30 PM ET) or trigger manually
- [ ] Check P&L tracking on Paper Trading page

## Automated Trading Validation

- [ ] Verify Celery Beat is scheduling tasks: check `docker compose logs beat`
- [ ] Wait for `paper_rebalance_daily` to fire (10:00 AM ET)
- [ ] Verify rebalance log shows SUCCESS
- [ ] Wait for `paper_snapshot_daily` to fire (4:30 PM ET)
- [ ] Verify P&L chart updates on Paper Trading page
- [ ] Confirm Telegram alerts arrive (if configured)

## Live Trading Activation (Dry-Run First)

- [ ] Set `LIVE_DRY_RUN=true` and `ENABLE_LIVE_TRADING=true` in `.env`
- [ ] Restart: `docker compose restart api worker`
- [ ] Run pre-trade checklist via Live page > "Pre-trade Checklist"
- [ ] All checks pass
- [ ] Run dry-run rebalance via Live page > "Dry Run"
- [ ] Review dry-run orders - verify they look correct
- [ ] Monitor for 1-2 days of dry-run operation

## Live Trading Activation (Real)

- [ ] Set `LIVE_DRY_RUN=false` in `.env`
- [ ] Restart: `docker compose restart api worker`
- [ ] Set conservative limits:
  - `LIVE_MAX_EXEC_PER_HOUR=5`
  - `LIVE_MAX_ORDERS_PER_HOUR=50`
  - `LIVE_MAX_ORDER_PCT_NLV=0.30`
- [ ] Verify IB Gateway is connected (Live page > IB connection)
- [ ] Run pre-trade checklist one more time
- [ ] Execute first live rebalance with small allocation
- [ ] Monitor fills in IB and verify against orders
- [ ] Check Telegram for trade notifications

## Emergency Contacts

- Kill-switch: `POST /api/live/halt` or set `TRADING_HALT=true`
- IB support: ibkr.com/support
- Server: SSH `root@213.159.68.39`

## Post-Go-Live Monitoring (First Week)

- [ ] Daily: Check P&L tracking, verify fills match expectations
- [ ] Daily: Review Telegram alerts for any errors
- [ ] Every 2 days: Compare paper vs live performance
- [ ] End of week: Full review of all trades, P&L, and any anomalies
