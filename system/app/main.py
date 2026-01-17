import os
import logging
from quiver_signals import QuiverSignals
from ib_executor import IBExecutor

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration (Use environment variables for security)
QUIVER_API_KEY = os.getenv('QUIVER_API_KEY', 'YOUR_QUIVER_API_KEY')
IB_HOST = os.getenv('IB_HOST', '127.0.0.1')
IB_PORT = int(os.getenv('IB_PORT', 7497)) # 7497 for Paper, 7496 for Live
ALLOCATION_USD = 1000 # Dollars to invest per signal


def main():
    if QUIVER_API_KEY == 'YOUR_QUIVER_API_KEY':
        logging.error("Please set your QUIVER_API_KEY environment variable.")
        return

    # 1. Fetch Signals
    logging.info("Fetching signals from Quiver Quantitative...")
    qs = QuiverSignals(QUIVER_API_KEY)
    target_portfolio = qs.get_combined_portfolio()
    logging.info(f"Target Portfolio: {target_portfolio}")

    if not target_portfolio:
        logging.warning("No signals found. Skipping rebalance.")
        return

    # 2. Execute on IBKR
    logging.info("Live execution is currently disabled for testing.")
    # logging.info("Connecting to IBKR...")
    # ib_exec = IBExecutor(host=IB_HOST, port=IB_PORT)
    # ib_exec.connect()
    #
    # if ib_exec.ib.isConnected():
    #     logging.info("Starting rebalance...")
    #     ib_exec.rebalance(target_portfolio, allocation_per_stock_usd=ALLOCATION_USD)
    #
    #     # Give some time for orders to process
    #     ib_exec.ib.sleep(5)
    #     ib_exec.disconnect()
    #     logging.info("Disconnected from IBKR. Portfolio update complete.")
    # else:
    #     logging.error("Could not connect to IBKR. Ensure TWS/Gateway is running and API is enabled.")


if __name__ == "__main__":
    main()

