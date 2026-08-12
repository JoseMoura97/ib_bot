import asyncio
from ib_insync import *
import logging

try:  # Supports both package imports and the legacy ``system/app`` launcher.
    from .order_preflight import OrderPreFlightPolicy, order_pre_flight_guard
except ImportError:  # pragma: no cover - exercised by the legacy launcher only
    from order_preflight import OrderPreFlightPolicy, order_pre_flight_guard


class IBExecutor:
    def __init__(self, host='127.0.0.1', port=7497, client_id=1):
        self.ib = IB()
        self.host = host
        self.port = port
        self.client_id = client_id

    def connect(self):
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id)
            logging.info("Connected to IBKR")
        except Exception as e:
            logging.error(f"Failed to connect to IBKR: {e}")

    def get_current_positions(self, account=None):
        """Get current positions, optionally filtered by account."""
        positions = self.ib.positions(account) if account else self.ib.positions()
        return {p.contract.symbol: p.position for p in positions if p.position != 0}

    def get_account_value(self, account=None):
        """Get the net liquidation value of the account."""
        summary = self.ib.accountSummary(account) if account else self.ib.accountSummary()
        for item in summary:
            if item.tag == 'NetLiquidation':
                return float(item.value)
        return 0

    def _market_price(self, contract):
        [ticker_data] = self.ib.reqTickers(contract)
        price = ticker_data.marketPrice()
        return float(price) if price and price > 0 else None

    def _place_guarded_market_order(self, contract, side, quantity, account, price, aggregate_notional_usd):
        """Guard immediately before the only IB API order submission in this class."""
        order_notional = abs(float(quantity)) * float(price) if price is not None else None
        aggregate_notional = (
            float(aggregate_notional_usd) + float(order_notional)
            if order_notional is not None
            else None
        )
        order_pre_flight_guard(
            account_id=account,
            order_notional_usd=order_notional,
            aggregate_notional_usd=aggregate_notional,
            policy=OrderPreFlightPolicy.from_environment(),
        )
        order = MarketOrder(side, abs(quantity))
        if account:
            order.account = account
        self.ib.placeOrder(contract, order)
        return float(order_notional or 0.0)

    def rebalance(self, target_tickers, allocation_per_stock_usd=1000, account=None):
        """
        Simple rebalance - buys/sells to match target tickers.
        """
        current_positions = self.get_current_positions(account)
        submitted_notional = 0.0

        # 1. Sell tickers not in target
        for ticker, qty in current_positions.items():
            if ticker not in target_tickers:
                logging.info(f"Selling {qty} shares of {ticker}")
                contract = Stock(ticker, 'SMART', 'USD')
                self.ib.qualifyContracts(contract)
                price = self._market_price(contract)
                submitted_notional += self._place_guarded_market_order(
                    contract, 'SELL', qty, account, price, submitted_notional
                )

        # 2. Buy tickers in target but not in current
        for ticker in target_tickers:
            if ticker not in current_positions:
                logging.info(f"Buying {ticker}")
                contract = Stock(ticker, 'SMART', 'USD')
                self.ib.qualifyContracts(contract)

                price = self._market_price(contract)

                if price and price > 0:
                    qty = int(allocation_per_stock_usd / price)
                    if qty > 0:
                        submitted_notional += self._place_guarded_market_order(
                            contract, 'BUY', qty, account, price, submitted_notional
                        )
                    else:
                        logging.warning(f"Price for {ticker} too high for allocation.")
                else:
                    logging.warning(f"Could not get price for {ticker}")

    def rebalance_weighted(self, strategy_signals, strategies_config, account=None, total_allocation_pct=0.8):
        """
        Weighted rebalance based on strategy weights.

        Args:
            strategy_signals: Dict of {strategy_name: [tickers]}
            strategies_config: List of strategy configs with 'name', 'weight', 'enabled'
            account: Optional account ID
            total_allocation_pct: Percentage of NLV to allocate (default 80%)
        """
        # Get total portfolio value
        nlv = self.get_account_value(account)
        if nlv <= 0:
            logging.error("Could not get account value for weighted rebalance")
            return

        total_to_allocate = nlv * total_allocation_pct
        logging.info(f"Total NLV: ${nlv:,.2f}, Allocating: ${total_to_allocate:,.2f}")

        current_positions = self.get_current_positions(account)
        submitted_notional = 0.0

        # Calculate target allocation per ticker
        ticker_allocations = {}  # ticker -> target_usd_value

        for strat in strategies_config:
            if not strat.get('enabled', False):
                continue

            strat_name = strat['name']
            strat_weight = strat.get('weight', 0) / 100.0  # Convert to decimal
            strat_allocation = total_to_allocate * strat_weight

            tickers = strategy_signals.get(strat_name, [])
            if not tickers:
                continue

            # Equal allocation within strategy
            per_ticker = strat_allocation / len(tickers)

            for ticker in tickers:
                if ticker in ticker_allocations:
                    ticker_allocations[ticker] += per_ticker
                else:
                    ticker_allocations[ticker] = per_ticker

        logging.info(f"Target allocations: {ticker_allocations}")

        # 1. Sell positions not in target
        for ticker, qty in current_positions.items():
            if ticker not in ticker_allocations:
                logging.info(f"Selling all {qty} shares of {ticker} (not in target)")
                contract = Stock(ticker, 'SMART', 'USD')
                self.ib.qualifyContracts(contract)
                price = self._market_price(contract)
                submitted_notional += self._place_guarded_market_order(
                    contract, 'SELL', qty, account, price, submitted_notional
                )

        # 2. Adjust positions to match target allocations
        for ticker, target_value in ticker_allocations.items():
            contract = Stock(ticker, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)

            price = self._market_price(contract)

            if not price or price <= 0:
                logging.warning(f"Could not get price for {ticker}, skipping")
                continue

            current_qty = current_positions.get(ticker, 0)
            current_value = current_qty * price

            target_qty = int(target_value / price)
            qty_diff = target_qty - current_qty

            if abs(qty_diff) < 1:
                logging.info(f"{ticker}: Already at target ({current_qty} shares)")
                continue

            if qty_diff > 0:
                logging.info(f"{ticker}: Buying {qty_diff} shares (target: {target_qty}, current: {current_qty})")
                side = 'BUY'
            else:
                logging.info(f"{ticker}: Selling {abs(qty_diff)} shares (target: {target_qty}, current: {current_qty})")
                side = 'SELL'

            submitted_notional += self._place_guarded_market_order(
                contract, side, qty_diff, account, price, submitted_notional
            )
            self.ib.sleep(0.5)  # Small delay between orders

    def disconnect(self):
        self.ib.disconnect()

