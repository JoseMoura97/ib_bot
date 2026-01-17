import os
from ibind import IbkrClient
from dotenv import load_dotenv
import urllib3

# Disable SSL warnings for local gateway
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class IBWebClient:
    def __init__(self):
        load_dotenv()
        self.username = os.getenv('IB_USER')
        self.password = os.getenv('IB_PASS')
        self.base_url = "http://localhost:5000/v1/api"

        # Initialize ibind client for automated auth
        self.client = IbkrClient(
            url=self.base_url,
            cacert=False  # Skip SSL verify for local
        )

    def check_auth(self):
        """Checks if the session is currently authenticated."""
        try:
            return self.client.is_authenticated
        except Exception:
            return False

    def get_accounts(self):
        """Fetches all account IDs."""
        res = self.client.portfolio_accounts()
        return res.data if res.success else []

    def get_account_summary(self, account_id):
        """Fetches account summary (NLV, Margin, etc.)."""
        res = self.client.portfolio_account_summary(account_id)
        return res.data if res.success else {}

    def get_positions(self, account_id):
        """Fetches current positions."""
        res = self.client.portfolio_positions(account_id)
        return res.data if res.success else []

    def get_conid(self, ticker):
        """Helper to find the Contract ID for a ticker."""
        res = self.client.iserver_secdef_search(symbol=ticker)
        if res.success and isinstance(res.data, list) and len(res.data) > 0:
            return res.data[0].get('conid')
        return None

    def place_market_order(self, account_id, ticker, side, quantity):
        """Resolves ticker to conid and places a market order."""
        conid = self.get_conid(ticker)
        if not conid:
            return {"error": f"Could not find conid for {ticker}"}

        order = {
            "conid": int(conid),
            "orderType": "MKT",
            "side": side,
            "quantity": float(quantity),
            "tif": "DAY",
        }
        res = self.client.iserver_place_orders(account_id, orders=[order])
        return res.data if res.success else {"error": res.message}

