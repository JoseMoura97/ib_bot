#!/usr/bin/env python3
"""Download ProtonVPN OpenVPN config and set up connection."""
import requests, json, os, subprocess, sys

USERNAME = "6qN6WpF2BlBWJuW5"
PASSWORD = "jcLQZErPvbjOiTsYu5jh5huuYLShq3Od"

headers = {
    "x-pm-appversion": "LinuxVPN_3.3.0",
    "x-pm-apiversion": "3",
    "User-Agent": "ProtonVPN/3.3.0 (Linux)",
}

# Step 1: Get server list (public endpoint)
print("[*] Fetching ProtonVPN server list...")
r = requests.get("https://api.protonvpn.ch/vpn/logicals", headers=headers, timeout=15)
print(f"[*] Server list status: {r.status_code}")

if r.status_code == 200:
    data = r.json()
    servers = data.get("LogicalServers", [])
    # Pick a fast server - prefer Netherlands or Germany (close to Finland)
    candidates = [s for s in servers if s.get("Status") == 1 and s.get("ExitCountry") in ("NL", "DE", "SE", "FI") and s.get("Tier", 0) <= 3]
    if not candidates:
        candidates = [s for s in servers if s.get("Status") == 1 and s.get("Tier", 0) <= 3]
    if candidates:
        # Pick by lowest load
        server = sorted(candidates, key=lambda x: x.get("Load", 100))[0]
        print(f"[*] Selected server: {server['Name']} ({server.get('ExitCountry')}) Load: {server.get('Load')}%")
        # Get server entry IPs
        entry_ips = []
        for s in server.get("Servers", []):
            entry_ips.append(s.get("EntryIP"))
        server_ip = entry_ips[0] if entry_ips else None
        print(f"[*] Server IP: {server_ip}")
    else:
        print("[!] No suitable servers found")
        sys.exit(1)
else:
    print(f"[!] Failed to get server list: {r.text[:200]}")
    sys.exit(1)

# Step 2: Download ProtonVPN CA cert
print("[*] Downloading ProtonVPN CA cert...")
ca_r = requests.get("https://protonvpn.com/download/ProtonVPN_public_key_certificate.pem", timeout=15)
if ca_r.status_code == 200:
    ca_cert = ca_r.text
    print("[*] CA cert downloaded")
else:
    print(f"[!] Failed to download CA cert: {ca_r.status_code}")
    sys.exit(1)

# Step 3: Write config files
os.makedirs("/etc/openvpn/protonvpn", exist_ok=True)

# Write CA cert
with open("/etc/openvpn/protonvpn/ca.crt", "w") as f:
    f.write(ca_cert)

# Write auth file
with open("/etc/openvpn/protonvpn/auth.txt", "w") as f:
    f.write(f"{USERNAME}\n{PASSWORD}\n")
os.chmod("/etc/openvpn/protonvpn/auth.txt", 0o600)

# Write OpenVPN config
ovpn_config = f"""client
dev tun
proto udp
remote {server_ip} 1194
resolv-retry infinite
nobind
persist-key
persist-tun
ca /etc/openvpn/protonvpn/ca.crt
tls-client
remote-cert-tls server
auth-user-pass /etc/openvpn/protonvpn/auth.txt
verb 3
cipher AES-256-CBC
auth SHA512
ping 60
ping-restart 120
sndbuf 0
rcvbuf 0
redirect-gateway def1
dhcp-option DNS 10.8.8.1
"""

with open("/etc/openvpn/protonvpn/protonvpn.conf", "w") as f:
    f.write(ovpn_config)

print(f"[*] Config written for server {server_ip}")
print("[*] Starting OpenVPN...")
result = subprocess.run(
    ["openvpn", "--config", "/etc/openvpn/protonvpn/protonvpn.conf", "--daemon", "--log", "/var/log/openvpn-proton.log"],
    capture_output=True, text=True
)
if result.returncode == 0:
    print("[*] OpenVPN started as daemon")
else:
    print(f"[!] OpenVPN error: {result.stderr}")
    sys.exit(1)

import time
time.sleep(5)
# Check if tun0 is up
r2 = subprocess.run(["ip", "addr", "show", "tun0"], capture_output=True, text=True)
if "inet" in r2.stdout:
    print("[+] VPN connected! tun0 is up.")
    subprocess.run(["curl", "-s", "https://ifconfig.me"], check=False)
else:
    print("[!] tun0 not up yet, check /var/log/openvpn-proton.log")
    print(r2.stdout)
