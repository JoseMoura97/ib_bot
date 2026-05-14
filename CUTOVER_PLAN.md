# IB Bot — Finland → EPYC Cutover Plan
**Target:** Decommission `213.159.68.39` (THE.Hosting Finland VPS)  
**Generated:** 2026-05-09 | Status: **IN PROGRESS — Step 1 needed from you**

---

## What the agent already completed (2026-05-09)

| Item | Status |
|---|---|
| Log rotation (`/etc/logrotate.d/srv-logs`) — daily, 14d, 200MB max | ✅ Done |
| Docker log rotation (`/etc/docker/daemon.json`) — 50MB×5 per container | ✅ Done |
| `docker-compose.yml` port conflicts fixed (db:5432, redis:6379, web:3000 removed) | ✅ Done |
| `xvfb-ibgw.service` — virtual display :1, enabled + running | ✅ Done |
| `x11vnc`, `socat`, `xautomation` installed | ✅ Done |
| **IB Gateway 10.45** installed at `/opt/ibgateway/` | ✅ Done |
| **IBC 3.23.0** installed at `/opt/ibc/` | ✅ Done |
| `/opt/ibc/config.ini` — template written (credentials needed) | ⚠️ Needs your creds |
| `/opt/ibc/auto2fa.py` — template written (TOTP secret needed) | ⚠️ Needs TOTP secret |
| `/opt/ibc/start-gateway.sh` — startup script | ✅ Done |
| `ibgateway.service` + `ib-socat.service` — written, **NOT enabled** (intentional) | ✅ Ready |
| `docker-compose.epyc.yml` — 3 commented modes (shadow/paper/live) | ✅ Updated |

---

## Cutover Steps

### Step 1 — Copy credentials from Finland **[YOU]**

SSH from your laptop (not EPYC — key not authorized on Finland):

```bash
ssh root@213.159.68.39

# Extract TOTP secret
cat /opt/ibc/auto2fa.py | grep TOTP_SECRET

# Extract IBC login
cat /opt/ibc/config.ini | grep -E "IbLoginId|IbPassword"
```

Then fill in on EPYC:
```bash
# Via SSH to EPYC:
nano /opt/ibc/auto2fa.py   # set TOTP_SECRET="..."
nano /opt/ibc/config.ini   # set IbLoginId=..., IbPassword=...

# Copy jts.ini (saved IB Gateway settings):
scp root@213.159.68.39:/root/Jts/jts.ini root@100.67.188.93:/root/Jts/jts.ini
```

---

### Step 2 — First manual IB Gateway login via VNC **[YOU]**

> ⚠️ **2FA lockout risk**: jibas.bot was rate-limited before. Do NOT let IBC handle
> 2FA automatically on first login. Login manually via VNC. Don't rush.

```bash
# 1. On EPYC via SSH — start gateway:
DISPLAY=:1 nohup /opt/ibgateway/ibgateway > /tmp/gw.log 2>&1 &
tail -f /tmp/gw.log

# 2. From your laptop — SSH tunnel for VNC:
ssh -L 5900:localhost:5900 servidor@100.67.188.93 -N &
# Connect TightVNC / RealVNC to localhost:5900
# Login: jibas.bot credentials + TOTP from Google Authenticator

# 3. In Gateway GUI:
#    Configure → Settings → API Settings
#    ✓ Enable ActiveX and Socket Clients
#    Port: 4001
#    "Allow connections from localhost only" — leave checked (socat handles Docker)
```

---

### Step 3 — Verify Gateway port + start socat **[AGENT can do this]**

Tell the agent: "IB Gateway is logged in, verify ports and start socat"

```bash
ss -tlnp | grep 4001   # expect LISTEN on 127.0.0.1:4001
sudo systemctl start ib-socat
ss -tlnp | grep 4003   # expect 0.0.0.0:4003
```

---

### Step 4 — Switch to paper mode and test connection **[AGENT]**

Agent edits `docker-compose.epyc.yml` to uncomment paper block, then:
```bash
cd ~/Desktop/cursor-projects/ib_bot
docker compose -f docker-compose.yml -f docker-compose.epyc.yml \
  up -d --force-recreate api worker beat

curl -s http://127.0.0.1:8001/ib/status
# Expected: {"connected": true, "accounts": ["U15721390", ...]}
```

---

### Step 5 — Paper trading 24–48h **[YOU watch]**

Dashboard: `http://100.67.188.93:8090/`  
Confirm: portfolio snapshots, price data, rebalance logic.  
Both Finland and EPYC run in parallel — Finland stays live.

Enable autostart for reboot survival:
```bash
sudo systemctl enable ibgateway ib-socat
```

---

### Step 6 — Flip to live **[YOU must explicitly confirm]**

Agent does NOT do this autonomously. You say "flip ib_bot to live on EPYC".

Agent will uncomment live block in `docker-compose.epyc.yml`:
```yaml
IB_HOST: "host.docker.internal"
IB_PORT: "4003"
ENABLE_LIVE_TRADING: "true"
LIVE_DRY_RUN: "false"
```
Then force-recreate api/worker/beat.

---

### Step 7 — Stop Finland **[YOU]**

After EPYC live is confirmed. Keep Finland alive 48h for rollback.

```bash
ssh root@213.159.68.39
cd /home/ibbot/ib_bot
# Optional DB backup first:
docker compose exec db pg_dump -U ibbot ibbot | gzip > /home/ibbot/backups/final-$(date +%Y%m%d).sql.gz
docker compose down
pkill -f ibgateway
systemctl stop ibgateway ib-socat 2>/dev/null
```

---

### Step 8 — Decommission VPS **[YOU]**

After 48h, no rollback:
```bash
# Save final backups:
scp -r root@213.159.68.39:/home/ibbot/backups/ ~/Desktop/cursor-projects/ib_bot/finland-backups/
scp root@213.159.68.39:/root/Jts/jts.ini ~/Desktop/cursor-projects/ib_bot/finland-backups/
```
Then cancel at THE.Hosting control panel. ~€15–25/month freed.

---

## Port map (EPYC after cutover)

| Port | Service | Access |
|---|---|---|
| 4001 | IB Gateway API (localhost only) | localhost |
| 4003 | socat bridge → 4001 (for Docker) | Docker internal |
| 5900 | x11vnc display :1 (VNC GUI access) | SSH tunnel only |
| 8001 | ib_bot FastAPI (Docker → host) | Tailscale |
| 8090 | ib_bot nginx dashboard | Tailscale |

---

## Key warnings
- **Never set `SecondFactorDevice`** in IBC config — causes rapid 2FA and lockout
- **`jibas.gateway` sub-user is pending approval** — do NOT use, only `jibas.bot`
- **Docker gateway IP** may be `172.18.0.1` not `172.17.0.1` — verify with `docker inspect` if direct IB connect is needed (socat avoids this)
- **IB Gateway 10.45** vs Finland's 10.37 — config format is the same, `jts.ini` copies over cleanly
