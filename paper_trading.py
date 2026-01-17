"""
Paper Trading Engine
Simulates trades without executing them, tracks virtual portfolio with real prices.
"""

import sqlite3
import pandas as pd
from datetime import datetime
from ib_insync import Stock
import logging

DB_FILE = 'portfolio_history.db'

def init_paper_db():
    """Initialize paper trading tables."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Paper portfolio - tracks virtual positions
    c.execute('''CREATE TABLE IF NOT EXISTS paper_positions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  ticker TEXT NOT NULL,
                  quantity REAL NOT NULL,
                  avg_cost REAL NOT NULL,
                  currency TEXT DEFAULT 'USD',
                  strategy TEXT,
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # Paper trades - log of all simulated trades
    c.execute('''CREATE TABLE IF NOT EXISTS paper_trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  ticker TEXT NOT NULL,
                  action TEXT NOT NULL,
                  quantity REAL NOT NULL,
                  price REAL NOT NULL,
                  value REAL NOT NULL,
                  strategy TEXT,
                  notes TEXT)''')
    
    # Paper cash balance
    c.execute('''CREATE TABLE IF NOT EXISTS paper_cash
                 (id INTEGER PRIMARY KEY,
                  balance REAL NOT NULL,
                  currency TEXT DEFAULT 'USD',
                  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # Initialize cash if not exists
    c.execute('SELECT COUNT(*) FROM paper_cash')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO paper_cash (id, balance, currency) VALUES (1, 100000, "USD")')
    
    conn.commit()
    conn.close()

init_paper_db()


class PaperTradingEngine:
    def __init__(self, ib_connection=None):
        """
        Args:
            ib_connection: Optional IB connection for real-time prices. 
                          If None, uses avg_cost for valuations.
        """
        self.ib = ib_connection
        self.db_file = DB_FILE
    
    def get_cash_balance(self):
        """Get current paper cash balance."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('SELECT balance FROM paper_cash WHERE id = 1')
        result = c.fetchone()
        conn.close()
        return result[0] if result else 0
    
    def set_cash_balance(self, amount):
        """Set paper cash balance (for deposits/withdrawals)."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('UPDATE paper_cash SET balance = ?, updated_at = ? WHERE id = 1',
                  (amount, datetime.now()))
        conn.commit()
        conn.close()
    
    def deposit(self, amount):
        """Add cash to paper account."""
        current = self.get_cash_balance()
        self.set_cash_balance(current + amount)
        logging.info(f"Paper deposit: ${amount:,.2f}. New balance: ${current + amount:,.2f}")
        return current + amount
    
    def withdraw(self, amount):
        """Remove cash from paper account."""
        current = self.get_cash_balance()
        if amount > current:
            raise ValueError(f"Insufficient funds. Balance: ${current:,.2f}, Requested: ${amount:,.2f}")
        self.set_cash_balance(current - amount)
        return current - amount
    
    def get_positions(self):
        """Get all paper positions."""
        conn = sqlite3.connect(self.db_file)
        df = pd.read_sql_query(
            'SELECT ticker, quantity, avg_cost, currency, strategy FROM paper_positions WHERE quantity != 0',
            conn
        )
        conn.close()
        return df
    
    def get_position(self, ticker):
        """Get position for a specific ticker."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('SELECT quantity, avg_cost FROM paper_positions WHERE ticker = ?', (ticker,))
        result = c.fetchone()
        conn.close()
        return {'quantity': result[0], 'avg_cost': result[1]} if result else None
    
    def get_current_prices(self, tickers):
        """Get current market prices for a list of tickers in one batch."""
        prices = {ticker: None for ticker in tickers}
        
        if self.ib and self.ib.isConnected() and tickers:
            try:
                contracts = [Stock(ticker, 'SMART', 'USD') for ticker in tickers]
                self.ib.qualifyContracts(*contracts)
                ticker_data_list = self.ib.reqTickers(*contracts)
                
                for t_data in ticker_data_list:
                    price = t_data.marketPrice()
                    if price != price or price is None or price <= 0:
                        price = t_data.last if (t_data.last == t_data.last and t_data.last > 0) else t_data.close
                    
                    if price == price and price is not None and price > 0:
                        prices[t_data.contract.symbol] = price
            except Exception as e:
                logging.warning(f"Error fetching batch prices: {e}")
        
        return prices

    def get_current_price(self, ticker):
        """Get current market price for a ticker."""
        if self.ib and self.ib.isConnected():
            try:
                contract = Stock(ticker, 'SMART', 'USD')
                self.ib.qualifyContracts(contract)
                [ticker_data] = self.ib.reqTickers(contract)
                price = ticker_data.marketPrice()
                if price and price > 0:
                    return price
            except:
                pass
        
        # Fallback: use last known price from positions
        pos = self.get_position(ticker)
        return pos['avg_cost'] if pos else None
    
    def execute_paper_trade(self, ticker, action, quantity, price=None, strategy=None, notes=None):
        """
        Execute a paper trade.
        
        Args:
            ticker: Stock symbol
            action: 'BUY' or 'SELL'
            quantity: Number of shares
            price: Price per share (if None, fetches current price)
            strategy: Optional strategy name for tracking
            notes: Optional notes
        """
        if price is None:
            price = self.get_current_price(ticker)
            if price is None:
                raise ValueError(f"Could not get price for {ticker}")
        
        value = quantity * price
        action = action.upper()
        
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        
        # Get current position
        c.execute('SELECT id, quantity, avg_cost FROM paper_positions WHERE ticker = ?', (ticker,))
        current = c.fetchone()
        
        if action == 'BUY':
            # Check cash
            cash = self.get_cash_balance()
            if value > cash:
                conn.close()
                raise ValueError(f"Insufficient cash. Need ${value:,.2f}, have ${cash:,.2f}")
            
            if current:
                # Update existing position (average cost)
                pos_id, curr_qty, curr_avg = current
                new_qty = curr_qty + quantity
                new_avg = ((curr_qty * curr_avg) + (quantity * price)) / new_qty
                c.execute('''UPDATE paper_positions 
                            SET quantity = ?, avg_cost = ?, updated_at = ?, strategy = COALESCE(?, strategy)
                            WHERE id = ?''',
                         (new_qty, new_avg, datetime.now(), strategy, pos_id))
            else:
                # Create new position
                c.execute('''INSERT INTO paper_positions (ticker, quantity, avg_cost, strategy)
                            VALUES (?, ?, ?, ?)''',
                         (ticker, quantity, price, strategy))
            
            # Deduct cash
            self.set_cash_balance(cash - value)
            
        elif action == 'SELL':
            if not current or current[1] < quantity:
                conn.close()
                available = current[1] if current else 0
                raise ValueError(f"Insufficient shares. Have {available}, trying to sell {quantity}")
            
            pos_id, curr_qty, curr_avg = current
            new_qty = curr_qty - quantity
            
            # Update position
            c.execute('UPDATE paper_positions SET quantity = ?, updated_at = ? WHERE id = ?',
                     (new_qty, datetime.now(), pos_id))
            
            # Add cash (proceeds from sale)
            cash = self.get_cash_balance()
            self.set_cash_balance(cash + value)
        
        # Log the trade
        c.execute('''INSERT INTO paper_trades (ticker, action, quantity, price, value, strategy, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                 (ticker, action, quantity, price, value, strategy, notes))
        
        conn.commit()
        conn.close()
        
        logging.info(f"Paper {action}: {quantity} {ticker} @ ${price:.2f} = ${value:,.2f}")
        return {'ticker': ticker, 'action': action, 'quantity': quantity, 'price': price, 'value': value}
    
    def get_trade_history(self, limit=50):
        """Get recent paper trades."""
        conn = sqlite3.connect(self.db_file)
        df = pd.read_sql_query(
            f'SELECT * FROM paper_trades ORDER BY timestamp DESC LIMIT {limit}',
            conn
        )
        conn.close()
        return df
    
    def get_portfolio_value(self):
        """Calculate total portfolio value (cash + positions)."""
        cash = self.get_cash_balance()
        positions = self.get_positions()
        
        if positions.empty:
            return {'cash': cash, 'positions_value': 0, 'total': cash, 'positions': []}
        
        pos_details = []
        total_pos_value = 0
        
        # Batch fetch all prices at once
        tickers = positions['ticker'].tolist()
        prices = self.get_current_prices(tickers)
        
        for _, row in positions.iterrows():
            ticker = row['ticker']
            current_price = prices.get(ticker)
            
            if current_price is None:
                current_price = row['avg_cost']
            
            market_value = row['quantity'] * current_price
            cost_basis = row['quantity'] * row['avg_cost']
            pnl = market_value - cost_basis
            pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0
            
            pos_details.append({
                'ticker': row['ticker'],
                'quantity': row['quantity'],
                'avg_cost': row['avg_cost'],
                'current_price': current_price,
                'market_value': market_value,
                'cost_basis': cost_basis,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'strategy': row['strategy']
            })
            total_pos_value += market_value
        
        return {
            'cash': cash,
            'positions_value': total_pos_value,
            'total': cash + total_pos_value,
            'positions': pos_details
        }
    
    def rebalance_paper(self, strategy_signals, strategies_config, allocation_pct=0.8):
        """
        Paper rebalance based on strategy weights.
        
        Args:
            strategy_signals: Dict of {strategy_name: [tickers]}
            strategies_config: List of strategy configs with 'name', 'weight', 'enabled'
            allocation_pct: Percentage of portfolio to allocate (default 80%)
        """
        portfolio = self.get_portfolio_value()
        total_value = portfolio['total']
        total_to_allocate = total_value * allocation_pct
        
        logging.info(f"Paper Rebalance: Total value ${total_value:,.2f}, Allocating ${total_to_allocate:,.2f}")
        
        # Calculate target allocation per ticker
        ticker_allocations = {}
        ticker_strategies = {}
        
        for strat in strategies_config:
            if not strat.get('enabled', False):
                continue
            
            strat_name = strat['name']
            strat_weight = strat.get('weight', 0) / 100.0
            strat_allocation = total_to_allocate * strat_weight
            
            tickers = strategy_signals.get(strat_name, [])
            if not tickers:
                continue
            
            per_ticker = strat_allocation / len(tickers)
            
            for ticker in tickers:
                if ticker in ticker_allocations:
                    ticker_allocations[ticker] += per_ticker
                else:
                    ticker_allocations[ticker] = per_ticker
                    ticker_strategies[ticker] = strat_name
        
        # Get current positions
        current_positions = {row['ticker']: row['quantity'] 
                           for _, row in self.get_positions().iterrows()}
        
        trades_executed = []
        
        # 1. Sell positions not in target
        for ticker, qty in current_positions.items():
            if ticker not in ticker_allocations and qty > 0:
                price = self.get_current_price(ticker)
                if price:
                    trade = self.execute_paper_trade(ticker, 'SELL', qty, price, notes='Rebalance - not in target')
                    trades_executed.append(trade)
        
        # 2. Adjust positions to match target
        for ticker, target_value in ticker_allocations.items():
            price = self.get_current_price(ticker)
            if not price:
                logging.warning(f"Could not get price for {ticker}, skipping")
                continue
            
            current_qty = current_positions.get(ticker, 0)
            current_value = current_qty * price
            target_qty = int(target_value / price)
            qty_diff = target_qty - current_qty
            
            if abs(qty_diff) < 1:
                continue
            
            strategy = ticker_strategies.get(ticker)
            
            if qty_diff > 0:
                try:
                    trade = self.execute_paper_trade(ticker, 'BUY', qty_diff, price, strategy, 'Rebalance')
                    trades_executed.append(trade)
                except ValueError as e:
                    logging.warning(f"Could not buy {ticker}: {e}")
            else:
                trade = self.execute_paper_trade(ticker, 'SELL', abs(qty_diff), price, strategy, 'Rebalance')
                trades_executed.append(trade)
        
        return trades_executed
    
    def reset_paper_account(self, starting_cash=100000):
        """Reset paper account to fresh state."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('DELETE FROM paper_positions')
        c.execute('DELETE FROM paper_trades')
        c.execute('UPDATE paper_cash SET balance = ?, updated_at = ? WHERE id = 1',
                 (starting_cash, datetime.now()))
        conn.commit()
        conn.close()
        logging.info(f"Paper account reset. Starting cash: ${starting_cash:,.2f}")
