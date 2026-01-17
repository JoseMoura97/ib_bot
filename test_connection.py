from ib_web_client import IBWebClient
import json

client = IBWebClient()
print(f"Base URL: {client.base_url}")
auth = client.check_auth()
print(f"Is Authenticated: {auth}")

if not auth:
    # Try a raw request to see the error
    import requests
    try:
        res = requests.get("http://localhost:5000/v1/api/iserver/auth/status", timeout=5)
        print(f"Raw Status Code: {res.status_code}")
        print(f"Raw Response: {res.text}")
    except Exception as e:
        print(f"Raw Request Error: {e}")
