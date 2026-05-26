# ibeam Session Management

Manages Interactive Brokers Web API sessions via [ibeam](https://github.com/Voyz/ibeam) Docker containers.

## Primary Account — Quick Start

```bash
cd infra/ibeam

# Start the primary ibeam container (port 5055)
docker compose up -d

# Tail logs (login takes ~30-60 seconds)
docker logs -f ibeam-primary

# Verify session is authenticated
python3 test_session.py
```

## Session Manager (multi-user)

The session manager runs on port 5056 and dynamically spins up one ibeam container per account.

```bash
# Install dependencies
pip install fastapi uvicorn docker httpx

# Start the manager
uvicorn session_manager:app --host 0.0.0.0 --port 5056
```

### Add a new user account

```bash
curl -X POST http://localhost:5056/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "account": "user@example.com",
    "password": "secret",
    "totp_key": "BASE32TOTPKEY"
  }'
```

Response includes the `port` the new container was bound to.

### List all sessions

```bash
curl http://localhost:5056/sessions
```

### Check one session's auth status

```bash
curl http://localhost:5056/sessions/<account>/status
```

### Proxy an ibeam API call

```bash
# Any ibeam endpoint — /v1/api/<path> — is proxied transparently
curl http://localhost:5056/sessions/<account>/proxy/iserver/auth/status
curl http://localhost:5056/sessions/<account>/proxy/portfolio/accounts
```

### Remove a session

```bash
curl -X DELETE http://localhost:5056/sessions/<account>
```

## Keepalive

IB sessions expire after ~30 minutes of inactivity. The keepalive script tickles all running ibeam containers every 55 seconds.

```bash
python3 keepalive.py
```

Run it as a background service or in a `screen`/`tmux` session.

## Notes

- ibeam exposes HTTPS on port 5000 internally; all calls use `verify=False` (self-signed cert).
- The primary container maps 5055 → 5000; dynamic containers start at 5060.
- Container restart policy is `unless-stopped` — ibeam will auto-re-authenticate on Docker restart.
- `IBEAM_KEY` is a base32 TOTP secret (pyotp-compatible), same format as `auto2fa.py`.
- If keepalive reports `SESSION DEAD`, the `unless-stopped` restart policy will recover it automatically.
