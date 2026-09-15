import os
import math
import re
from ibind import IbkrClient
from dotenv import load_dotenv
import urllib3
from threading import Lock
from typing import Any, Callable

try:
    from .order_preflight import OrderPreFlightPolicy, order_pre_flight_guard
    from .gateway_state import GatewayState, assert_gateway_execution_ready
except ImportError:  # pragma: no cover - legacy direct script import
    from order_preflight import OrderPreFlightPolicy, order_pre_flight_guard
    from gateway_state import GatewayState, assert_gateway_execution_ready

# Disable SSL warnings for local gateway
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class WebOrderValidationError(ValueError):
    """A Client Portal order was malformed before any broker interaction."""


_TICKER = re.compile(r"^[A-Z][A-Z0-9.\-]{0,15}$")


def _default_gateway_state_provider() -> GatewayState:
    """Read the shared, socket-free Gateway snapshot.

    The web client must not probe or wake a dormant Gateway merely to decide
    whether a submission is allowed.  If this legacy module is run outside of
    the backend state service, no trustworthy snapshot exists, so fail closed.
    """
    try:
        from app.services.ib_worker import current_ib_gateway_state

        return current_ib_gateway_state()
    except Exception:
        return GatewayState(False, None, "shared Gateway state unavailable", True, "unknown")


class IBWebClient:
    def __init__(self, gateway_state_provider: Callable[[], GatewayState] | None = None):
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
        # A key is retained even if Client Portal returns an error: its order
        # may have reached the broker, so retrying it would be unsafe.
        self._submitted_idempotency_keys: set[str] = set()
        self._gateway_state_provider = gateway_state_provider or _default_gateway_state_provider

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

    @staticmethod
    def _validate_market_order(
        account_id: Any,
        ticker: Any,
        side: Any,
        quantity: Any,
        estimated_price: Any,
        idempotency_key: Any,
    ) -> tuple[str, str, str, float, float | None, str]:
        """Normalize only a well-formed market-order request.

        This occurs before contract resolution, so malformed input cannot
        reach either the order endpoint or an accidental alternate wrapper.
        """
        if not isinstance(account_id, str) or not account_id.strip():
            raise WebOrderValidationError("account_id must be a non-empty string")
        if not isinstance(ticker, str) or not _TICKER.fullmatch(ticker.strip().upper()):
            raise WebOrderValidationError("ticker must be a simple IB equity symbol")
        if not isinstance(side, str) or side.strip().upper() not in {"BUY", "SELL"}:
            raise WebOrderValidationError("side must be BUY or SELL")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise WebOrderValidationError("idempotency_key is required for Client Portal orders")
        try:
            normalized_quantity = float(quantity)
        except (TypeError, ValueError) as exc:
            raise WebOrderValidationError("quantity must be a finite positive number") from exc
        if not math.isfinite(normalized_quantity) or normalized_quantity <= 0.0:
            raise WebOrderValidationError("quantity must be a finite positive number")

        normalized_price: float | None = None
        if estimated_price is not None:
            try:
                normalized_price = float(estimated_price)
            except (TypeError, ValueError) as exc:
                raise WebOrderValidationError("estimated_price must be a finite positive number") from exc
            if not math.isfinite(normalized_price) or normalized_price <= 0.0:
                raise WebOrderValidationError("estimated_price must be a finite positive number")

        return (
            account_id.strip(),
            ticker.strip().upper(),
            side.strip().upper(),
            normalized_quantity,
            normalized_price,
            idempotency_key.strip(),
        )

    def _submit_guarded_order(
        self,
        *,
        account_id: str,
        order: dict[str, Any],
        order_notional_usd: float | None,
        idempotency_key: str,
    ):
        """The only Client Portal submission choke point.

        Keep the state, policy and idempotency checks in the same lock as the
        submission.  This leaves no wrapper with a route around the shared
        account/halt/notional/Gateway fences.
        """
        with self._notional_lock:
            assert_gateway_execution_ready(self._gateway_state_provider())
            order_pre_flight_guard(
                account_id=account_id,
                order_notional_usd=order_notional_usd,
                aggregate_notional_usd=(self._submitted_notional_usd + order_notional_usd)
                if order_notional_usd is not None
                else None,
                policy=OrderPreFlightPolicy.from_environment(),
            )
            if idempotency_key in self._submitted_idempotency_keys:
                raise WebOrderValidationError("idempotency_key has already been submitted")

            # Reserve before the irreversible call.  An error response is not
            # proof that Client Portal did not accept the order.
            self._submitted_idempotency_keys.add(idempotency_key)
            res = self.client.iserver_place_orders(account_id, orders=[order])
            if res.success:
                self._submitted_notional_usd += float(order_notional_usd or 0.0)
            return res

    def place_market_order(self, account_id, ticker, side, quantity, estimated_price=None, *, idempotency_key=None):
        """Resolves ticker to conid and places a market order.

        When absolute caps are armed callers must provide a current
        ``estimated_price``; an unpriced market order is refused fail-closed.
        """
        account_id, ticker, side, quantity, estimated_price, idempotency_key = self._validate_market_order(
            account_id, ticker, side, quantity, estimated_price, idempotency_key
        )
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
        order_notional = quantity * estimated_price if estimated_price is not None else None
        res = self._submit_guarded_order(
            account_id=account_id,
            order=order,
            order_notional_usd=order_notional,
            idempotency_key=idempotency_key,
        )
        return res.data if res.success else {"error": res.message}

