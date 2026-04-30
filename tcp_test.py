import socket, sys

for ip in ['127.0.0.1', '172.17.0.1', '172.18.0.1', '172.18.0.7', '172.19.0.1']:
    try:
        s = socket.socket()
        s.settimeout(3)
        s.connect((ip, 4001))
        s.close()
        print(f"OPEN   {ip}:4001")
    except Exception as e:
        print(f"CLOSED {ip}:4001  ({type(e).__name__}: {e})")

# Now try actual IB connect
print("\n--- ib_insync connect test ---")
import asyncio
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from ib_insync import IB
for ip in ['172.18.0.1', '172.17.0.1']:
    ib = IB()
    try:
        ib.connect(ip, 4001, clientId=50, timeout=5, readonly=True)
        print(f"IB CONNECTED via {ip}")
        print("Accounts:", ib.managedAccounts())
        ib.disconnect()
        break
    except Exception as e:
        print(f"IB FAIL {ip}: {e}")
