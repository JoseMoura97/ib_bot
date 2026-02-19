# Staging / Production Checklist

## Secrets and credentials

- Set `QUIVER_API_KEY`
- Set non-default `POSTGRES_USER` / `POSTGRES_PASSWORD`
- Ensure `.env` is not committed

## IB Gateway / TWS

- Enable API access in IB Gateway/TWS
- Confirm `IB_HOST` and `IB_PORT`
- Confirm account IDs appear in `/live` and `/api/ib/accounts`

## Trading safety

- Keep `ENABLE_LIVE_TRADING=false` until paper is stable
- Validate all execution safety gates are enabled
- Define a clear “stop trading now” switch (`TRADING_HALT=1`)

## Data paths and backups

- Ensure `./.cache` is persisted and backed up if needed
- Back up the database regularly

## Monitoring

- Check container logs (`docker-compose logs -f`)
- Review `/live` audit log after each run
