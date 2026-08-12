import os
from ibind import IbkrClient
from dotenv import load_dotenv
import urllib3
from threading import Lock

try:
    from .order_preflight import OrderPreFlightPolicy, order_pre_flight_guard
except ImportError:  # pragma: no cover - legacy direct script import
    from order_preflight import OrderPreFlightPolicy, order_pre_flight_guard

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
        self._submitted_notional_usd = 0.0
        self._notional_lock = Lock()

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

    def place_market_order(self, account_id, ticker, side, quantity, estimated_price=None):
        """Resolves ticker to conid and places a market order.

        When absolute caps are armed callers must provide a current
        ``estimated_price``; an unpriced market order is refused fail-closed.
        """
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
        order_notional = abs(float(quantity)) * float(estimated_price) if estimated_price is not None else None
        with self._notional_lock:
            order_pre_flight_guard(
                account_id=account_id,
                order_notional_usd=order_notional,
                aggregate_notional_usd=(self._submitted_notional_usd + order_notional)
                if order_notional is not None
                else None,
                policy=OrderPreFlightPolicy.from_environment(),
            )
            res = self.client.iserver_place_orders(account_id, orders=[order])
            if res.success:
                self._submitted_notional_usd += float(order_notional or 0.0)
        return res.data if res.success else {"error": res.message}

