import asyncio
import nest_asyncio

# Fix for asyncio
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())
nest_asyncio.apply()

from ib_insync import *

async def test_connect():
    ib = IB()
    try:
        print("Attempting to connect to 127.0.0.1:4001...")
        # Ensuring we use connectAsync correctly in an awaited context
        await ib.connectAsync('127.0.0.1', 4001, clientId=99, timeout=10)
        print("Connected successfully!")
        if ib.wrapper.accounts:
            print(f"Account: {ib.wrapper.accounts[0]}")
        else:
            print("Connected, but no accounts found.")
        ib.disconnect()
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_connect())
