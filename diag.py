import subprocess, os, sys

# Network info
r = subprocess.run(['cat', '/etc/hosts'], capture_output=True, text=True)
print("=== /etc/hosts ===")
print(r.stdout)

# Find the default gateway (host IP from container perspective)
r2 = subprocess.run(['cat', '/proc/net/route'], capture_output=True, text=True)
print("=== /proc/net/route ===")
print(r2.stdout)

# Check what Python packages are available
r3 = subprocess.run(['pip', 'list'], capture_output=True, text=True)
print("=== pip packages (filtered) ===")
for line in r3.stdout.splitlines():
    if any(x in line.lower() for x in ['django', 'fastapi', 'flask', 'ib', 'celery', 'redis']):
        print(line)

# Check app structure
r4 = subprocess.run(['ls', '/app'], capture_output=True, text=True)
print("=== /app contents ===")
print(r4.stdout)

# Check env vars
print("=== Relevant ENV ===")
for k, v in os.environ.items():
    if any(x in k.upper() for x in ['IB', 'DB', 'REDIS', 'CELERY', 'DJANGO', 'API', 'HOST', 'PORT']):
        print(f"  {k}={v}")

# Try connecting to IB Gateway on different IPs
print("=== IB Gateway port scan ===")
import socket
for ip in ['127.0.0.1', '172.17.0.1', '172.18.0.1', '172.19.0.1', '172.20.0.1', '172.21.0.1']:
    try:
        s = socket.socket()
        s.settimeout(2)
        s.connect((ip, 4001))
        s.close()
        print(f"  {ip}:4001 OPEN")
    except Exception as e:
        print(f"  {ip}:4001 {type(e).__name__}")
