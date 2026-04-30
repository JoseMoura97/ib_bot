import hashlib, os, sys, configparser

password = os.environ.get("VPN_PASSWORD")
if not password:
    sys.exit("ERROR: VPN_PASSWORD environment variable is required")
pw_hash = hashlib.sha512(password.encode()).hexdigest()

config_dir = os.path.expanduser("~/.pvpn-cli")
os.makedirs(config_dir, exist_ok=True)

cfg = configparser.ConfigParser()
cfg["USER"] = {
    "username": "6qN6WpF2BlBWJuW5",
    "password": pw_hash,
    "tier": "3",
    "default_protocol": "udp",
    "initialized": "1",
    "dns_leak_protection": "1",
    "custom_dns": "None",
    "check_update_interval": "3",
    "killswitch": "0",
    "split_tunnel": "0",
    "api_domain": "https://api.protonvpn.ch",
}

with open(os.path.join(config_dir, "pvpn-cli.cfg"), "w") as f:
    cfg.write(f)

print("Config written to", os.path.join(config_dir, "pvpn-cli.cfg"))
print("PW hash:", pw_hash[:20] + "...")
