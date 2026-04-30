import requests, json

# Update IB connection target at runtime
r = requests.post("http://localhost:8000/ib/connect",
    json={"host": "172.18.0.1", "port": 4001},
    timeout=15)
print("POST /ib/connect:", r.status_code, r.text[:300])

# Check status
r2 = requests.get("http://localhost:8000/ib/status", timeout=15)
print("GET /ib/status:", r2.status_code, r2.text[:300])

# Try accounts
if r2.json().get("connected"):
    r3 = requests.get("http://localhost:8000/ib/accounts", timeout=15)
    print("GET /ib/accounts:", r3.status_code, r3.text[:300])
