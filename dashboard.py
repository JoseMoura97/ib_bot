"""
LEGACY FILE: Standalone Streamlit dashboard. Uses legacy SQLite-based paper trading
(paper_trading.py was removed). Paper tab is disabled; use the FastAPI/PostgreSQL
paper trading API instead.
"""
import nest_asyncio
import asyncio

# Fix for asyncio in Streamlit - Must be before ib_insync import
try:
    # Use get_event_loop_policy() for modern Python compatibility
    loop = asyncio.get_event_loop_policy().get_event_loop()
except Exception:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
nest_asyncio.apply()

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from ib_insync import *
from dotenv import load_dotenv
import os
import json
import logging
from quiver_signals import QuiverSignals
try:
    from paper_trading import PaperTradingEngine
except ImportError:
    PaperTradingEngine = None  # Legacy SQLite paper_trading.py removed; use API/PostgreSQL paper trading
from datetime import datetime, timedelta
from pathlib import Path

# Lazy import for backtesting (requires yfinance)
BacktestEngine = None
def get_backtest_engine():
    global BacktestEngine
    if BacktestEngine is None:
        try:
            from backtest_engine import BacktestEngine as BE
            BacktestEngine = BE
        except ImportError:
            return None
    return BacktestEngine

# Load environment variables
load_dotenv(override=True)
QUIVER_API_KEY = os.getenv('QUIVER_API_KEY')
IB_HOST = os.getenv('IB_HOST', '127.0.0.1')
IB_PORT = int(os.getenv('IB_PORT', 4001))

# Strategy Config File
STRATEGIES_FILE = 'strategies_config.json'

def load_strategies_config():
    if os.path.exists(STRATEGIES_FILE):
        with open(STRATEGIES_FILE, 'r') as f:
            return json.load(f)
    return {"strategies": [], "accounts": []}

def save_strategies_config(config):
    with open(STRATEGIES_FILE, 'w') as f:
        json.dump(config, f, indent=2)

# Initialize Database
def init_db():
    conn = sqlite3.connect('portfolio_history.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS nlv_history
                 (timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, nlv REAL, currency TEXT, account TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS trade_log
                 (timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, ticker TEXT, action TEXT, qty INTEGER, price REAL, account TEXT)''')
    conn.commit()
    conn.close()

init_db()

# Page Config
st.set_page_config(page_title="Quant Dashboard", layout="wide")

# Custom CSS for better aesthetics
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 10px;
        padding: 20px;
        border: 1px solid #0f3460;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #1a1a2e;
        border-radius: 8px;
    }
    .paper-mode {
        background: linear-gradient(135deg, #2d1b4e 0%, #1a1a2e 100%);
        border: 2px solid #9b59b6;
        border-radius: 10px;
        padding: 10px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

st.title("📊 Quant Command Center")

# Sidebar - Connection & Account Selection
st.sidebar.header("IBKR Connection")

import random

@st.cache_resource
def get_ib_connection(host, port):
    # Create a new instance for the cache
    ib = IB()
    try:
        # Use a random clientId to avoid "already in use" errors between sessions
        client_id = random.randint(10, 1000)
        ib.connect(host, port, clientId=client_id, readonly=True)
        
        # Request delayed market data if live is not available
        ib.reqMarketDataType(3) 
        
        return ib
    except Exception as e:
        return e

# Get connection
result = get_ib_connection(IB_HOST, IB_PORT)

# Check connection status and handle disconnected cached object
ib_connected = isinstance(result, IB) and result.isConnected()

if not ib_connected and isinstance(result, IB):
    # Cached object is disconnected, try to reconnect it
    try:
        client_id = random.randint(10, 1000)
        result.connect(IB_HOST, IB_PORT, clientId=client_id, readonly=True)
        ib_connected = result.isConnected()
    except Exception as e:
        result = e
        ib_connected = False

ib = result if ib_connected else None

if ib_connected:
    st.sidebar.success(f"Connected to Port {IB_PORT}")
    managed_accounts = ib.managedAccounts()
    st.sidebar.subheader("Account Selection")
    if len(managed_accounts) > 1:
        selected_account = st.sidebar.selectbox("Select Account", managed_accounts)
    else:
        selected_account = managed_accounts[0] if managed_accounts else None
        st.sidebar.info(f"Account: {selected_account}")
    
    st.sidebar.divider()
    auto_refresh = st.sidebar.checkbox("Auto-refresh Portfolio", value=False, help="If disabled, you must manually refresh portfolio data. This makes the dashboard much faster.")
else:
    st.sidebar.error("Disconnected")
    selected_account = None
    if st.sidebar.button("Retry Connection"):
        st.cache_resource.clear()
        st.rerun()

# Initialize Paper Trading Engine (works with or without IB connection)
# Legacy SQLite paper_trading.py was removed; paper_engine is None if import failed
paper_engine = PaperTradingEngine(ib_connection=ib if ib_connected else None) if PaperTradingEngine else None

# Tabs for different sections
tab_portfolio, tab_paper, tab_backtest, tab_strategies, tab_margins, tab_strategy_dashboard = st.tabs([
    "📈 Live Portfolio", 
    "📝 Paper Trading",
    "📊 Backtesting",
    "⚙️ Strategies", 
    "💰 Margins & Balances",
    "📊 Strategy Dashboard"
])


def _load_strategy_dashboard_html() -> str:
    """
    Load STRATEGY_DASHBOARD.html and inject plot_data (if present) so the embedded
    page can render charts without relying on file/relative fetch inside an iframe.
    """
    html_path = Path(__file__).with_name("STRATEGY_DASHBOARD.html")
    if not html_path.exists():
        return ""

    html_text = html_path.read_text(encoding="utf-8", errors="ignore")

    plot_path = Path(__file__).with_name(".cache") / "plot_data.json"
    if plot_path.exists():
        try:
            plot_data = json.loads(plot_path.read_text(encoding="utf-8"))
            injected = (
                "<script>\n"
                "/* Injected by Streamlit dashboard to serve local plot_data.json */\n"
                f"window.__IB_BOT_PLOT_DATA__ = {json.dumps(plot_data)};\n"
                "(function(){\n"
                "  const __origFetch = window.fetch;\n"
                "  window.fetch = function(input, init){\n"
                "    try {\n"
                "      if (typeof input === 'string' && (input === '.cache/plot_data.json' || input.endsWith('/.cache/plot_data.json'))) {\n"
                "        return Promise.resolve(new Response(JSON.stringify(window.__IB_BOT_PLOT_DATA__), {\n"
                "          status: 200,\n"
                "          headers: { 'Content-Type': 'application/json' }\n"
                "        }));\n"
                "      }\n"
                "    } catch (e) {}\n"
                "    return __origFetch(input, init);\n"
                "  };\n"
                "})();\n"
                "</script>\n"
            )
            if "</head>" in html_text:
                html_text = html_text.replace("</head>", injected + "</head>", 1)
            else:
                html_text = injected + html_text
        except Exception:
            # If plot data can't be parsed, just render the HTML as-is.
            pass

    return html_text


@st.cache_data(ttl=60)
def get_strategy_dashboard_html_cached() -> str:
    return _load_strategy_dashboard_html()

# Helper function to get strategy signals
@st.cache_data(ttl=3600) # Cache for 1 hour
def get_strategy_signals():
    if not QUIVER_API_KEY:
        return {}, []
    
    config = load_strategies_config()
    qs = QuiverSignals(QUIVER_API_KEY)
    strategy_signals = {}
    enabled_strategies = [s for s in config.get('strategies', []) if s.get('enabled', False)]
    
    for strat in enabled_strategies:
        strat_name = strat['name']
        try:
            # Dynamically fetch signals using the new engine logic in QuiverSignals
            signals = qs.engine.get_signals(strat_name)
            strategy_signals[strat_name] = signals
        except Exception as e:
            st.error(f"Error fetching signals for {strat_name}: {e}")
            strategy_signals[strat_name] = []
    
    return strategy_signals, enabled_strategies

@st.cache_data(ttl=60) # Cache account summary for 1 minute
def get_account_summary(_ib, selected_account=None):
    try:
        # For individual accounts, accountValues is more reliable than accountSummary (which is for groups)
        if selected_account:
            values = _ib.accountValues(selected_account)
            if not values:
                # Fallback to accountSummary if accountValues is empty
                values = _ib.accountSummary(group='All')
                values = [v for v in values if v.account == selected_account]
            return values
        else:
            values = _ib.accountValues()
            if not values:
                values = _ib.accountSummary(group='All')
            return values
    except Exception as e:
        logging.error(f"Error fetching account summary: {e}")
        return []

@st.cache_data(ttl=60) # Cache positions for 1 minute
def get_positions_data(_ib, selected_account=None):
    try:
        return _ib.positions(selected_account) if selected_account else _ib.positions()
    except Exception as e:
        error_msg = str(e)
        if "10275" in error_msg:
            logging.warning(f"Positions info not available yet (Account Approval Pending): {selected_account}")
            # Silently return empty list rather than logging error as critical
            return []
        logging.error(f"Error fetching positions: {e}")
        return []

# Helper to qualify contracts with session state caching
def qualify_contracts_cached(_ib, contracts):
    if 'qualified_contracts' not in st.session_state:
        st.session_state.qualified_contracts = {}
    
    to_qualify = []
    for c in contracts:
        # If it already has a conId, it's mostly qualified. 
        # Only qualify if we haven't seen it before and it's not already complete.
        if c.conId and c.conId != 0 and (c.conId in st.session_state.qualified_contracts or c.symbol):
            continue
        to_qualify.append(c)
    
    if to_qualify and _ib.isConnected():
        try:
            logging.info(f"Qualifying {len(to_qualify)} contracts...")
            # Use qualifyContractsAsync with a strict timeout to prevent UI hanging
            # ib_insync .run() will block until the timeout or completion
            _ib.qualifyContracts(*to_qualify)
            for c in to_qualify:
                if c.conId:
                    st.session_state.qualified_contracts[c.conId] = c
        except Exception as e:
            logging.error(f"Error qualifying contracts: {e}")
    
    return [st.session_state.qualified_contracts.get(c.conId, c) for c in contracts]

# ==================== LIVE PORTFOLIO TAB ====================
with tab_portfolio:
    if not ib_connected:
        st.warning(f"Please ensure IB Gateway/TWS is running on Port {IB_PORT} and API access is enabled.")
        if isinstance(result, Exception):
            st.code(f"Error: {str(result)}")
    else:
        # Manual refresh button
        if st.button("🔄 Refresh All Data"):
            if 'last_ticker_update' in st.session_state:
                del st.session_state.last_ticker_update
            if 'positions_data' in st.session_state:
                del st.session_state.positions_data
            st.rerun()

        # Account Summary
        summary = get_account_summary(ib, selected_account)
        
        if summary:
            df_summary = pd.DataFrame(summary)
            
            try:
                nlv_row = df_summary[df_summary['tag'] == 'NetLiquidation']
                maint_row = df_summary[df_summary['tag'] == 'MaintMarginReq']
                
                nlv = float(nlv_row['value'].iloc[0]) if not nlv_row.empty else 0
                base_curr = nlv_row['currency'].iloc[0] if not nlv_row.empty else 'USD'
                maint_margin = float(maint_row['value'].iloc[0]) if not maint_row.empty else 0
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Net Liquidation Value", f"{nlv:,.2f} {base_curr}")
                col2.metric("Maintenance Margin", f"{maint_margin:,.2f} {base_curr}")
                
                margin_health = (nlv - maint_margin) / nlv if nlv > 0 else 0
                col3.metric("Margin Health", f"{margin_health:.1%}")
                
            except Exception as e:
                st.warning(f"Error loading account metrics: {e}")
        
        # Positions with Market Value
        # Optimization: Only load positions if needed or forced refresh
        if 'positions_data' not in st.session_state:
            with st.spinner("Fetching positions..."):
                st.session_state.positions_data = get_positions_data(ib, selected_account)
        
        positions = st.session_state.get('positions_data', [])
        
        if positions:
            pos_data = []
            
            # Extract contracts. Positions from IBKR are ALREADY qualified (have conId).
            # We mostly just need the qualified versions for reqTickers to work reliably.
            contracts_all = [p.contract for p in positions]
            
            # Identify which ones we REALLY need to qualify (usually none for positions)
            needs_qualifying = [c for c in contracts_all if not (c.conId and c.conId != 0)]
            
            if needs_qualifying:
                with st.spinner(f"Qualifying {len(needs_qualifying)} contracts..."):
                    qualified_contracts = qualify_contracts_cached(ib, contracts_all)
            else:
                # If they all have conId, we just use them as is
                qualified_contracts = contracts_all
            
            # Map conId to qualified contract for easy lookup
            qualified_contract_map = {c.conId: c for c in qualified_contracts if c.conId}
            
            # Batch request tickers for all contracts
            current_time = datetime.now()
            # Increase update interval to 2 minutes to reduce API stress
            needs_ticker_update = ('last_ticker_update' not in st.session_state or 
                                 (current_time - st.session_state.last_ticker_update).total_seconds() > 120)
            
            if (auto_refresh or needs_ticker_update) and ib.isConnected():
                with st.spinner("Updating market prices..."):
                    try:
                        # Non-blocking request
                        st.session_state.tickers = ib.reqTickers(*qualified_contracts)
                        st.session_state.last_ticker_update = current_time
                    except Exception as e:
                        logging.error(f"Error requesting tickers: {e}")
            
            tickers = st.session_state.get('tickers', [])
            ticker_map = {t.contract.conId: t for t in tickers if t.contract}
            
            for p in positions:
                # Use the qualified contract from our map
                contract = qualified_contract_map.get(p.contract.conId, p.contract)
                ticker = ticker_map.get(contract.conId)
                
                if ticker:
                    current_price = ticker.marketPrice()
                    # Fallback to last/close if marketPrice is nan
                    if current_price != current_price or current_price is None or current_price == -1:
                        current_price = ticker.last if (ticker.last == ticker.last and ticker.last > 0) else ticker.close
                    
                    if current_price != current_price or current_price is None or current_price <= 0:
                        current_price = p.avgCost
                else:
                    current_price = p.avgCost
                
                market_value = abs(p.position * current_price)
                
                pos_data.append({
                    'Ticker': contract.symbol,
                    'Quantity': p.position,
                    'Avg Cost': round(p.avgCost, 2),
                    'Current Price': round(current_price, 2),
                    'Market Value': round(market_value, 2),
                    'Currency': contract.currency
                })
            
            df_pos = pd.DataFrame(pos_data)
            
            st.subheader("Portfolio Allocation (by Market Value)")
            fig = px.pie(
                df_pos, 
                values='Market Value', 
                names='Ticker', 
                title='',
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Set2
            )
            fig.update_layout(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font_color='white'
            )
            st.plotly_chart(fig, width='stretch')
            
            st.subheader("Position Details")
            st.dataframe(
                df_pos.style.format({
                    'Avg Cost': '{:,.2f}',
                    'Current Price': '{:,.2f}',
                    'Market Value': '{:,.2f}'
                }),
                width='stretch'
            )
        else:
            st.info("No open positions in this account.")
        
        # Quiver Signals Section
        st.divider()
        st.subheader("Quiver Strategy Signals")
        
        if QUIVER_API_KEY:
            with st.spinner("Fetching latest signals..."):
                strategy_signals, enabled_strategies = get_strategy_signals()
                
                all_signals = []
                for strat_name, tickers in strategy_signals.items():
                    weight = next((s['weight'] for s in enabled_strategies if s['name'] == strat_name), 0)
                    for ticker in tickers:
                        all_signals.append({
                            'Strategy': strat_name,
                            'Ticker': ticker,
                            'Weight': f"{weight}%"
                        })
                
                if all_signals:
                    df_signals = pd.DataFrame(all_signals)
                    st.dataframe(df_signals, width='stretch')
                    
                    unique_tickers = list(set([s['Ticker'] for s in all_signals]))
                    st.write(f"**Combined Signals ({len(unique_tickers)} tickers):** {', '.join(unique_tickers[:10])}{'...' if len(unique_tickers) > 10 else ''}")
                    
                    st.info("⚠️ Live Trading is currently disabled for testing.")
                    # if st.button("Execute Weighted Rebalance (Live)", type="primary"):
                    #     st.info("Rebalancing started...")
                    #     from ib_executor import IBExecutor
                    #     executor = IBExecutor(host=IB_HOST, port=IB_PORT, client_id=11)
                    #     executor.connect()
                    #     executor.rebalance_weighted(strategy_signals, enabled_strategies, account=selected_account)
                    #     executor.disconnect()
                    #     st.success("Rebalance complete!")
                else:
                    st.info("No active signals from enabled strategies.")
        else:
            st.warning("Quiver API Key missing in .env")

# ==================== PAPER TRADING TAB ====================
with tab_paper:
    st.markdown('<div class="paper-mode">', unsafe_allow_html=True)
    st.markdown("### 📝 Paper Trading Mode")
    st.markdown("*Simulate trades without real money. Uses real market prices when connected to IBKR.*")
    st.markdown('</div>', unsafe_allow_html=True)

    if paper_engine is None:
        st.warning("Legacy SQLite-based paper trading has been removed. Use the FastAPI paper trading API (PostgreSQL) instead.")
        st.stop()

    # Paper Portfolio Value
    portfolio = paper_engine.get_portfolio_value()
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💵 Cash", f"${portfolio['cash']:,.2f}")
    col2.metric("📊 Positions Value", f"${portfolio['positions_value']:,.2f}")
    col3.metric("💰 Total Value", f"${portfolio['total']:,.2f}")
    
    # Calculate total P&L
    if portfolio['positions']:
        total_pnl = sum(p['pnl'] for p in portfolio['positions'])
        total_pnl_pct = (total_pnl / portfolio['total'] * 100) if portfolio['total'] > 0 else 0
        col4.metric("📈 Total P&L", f"${total_pnl:,.2f}", f"{total_pnl_pct:+.2f}%")
    else:
        col4.metric("📈 Total P&L", "$0.00", "0.00%")
    
    # Paper Account Management
    st.divider()
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("Account Management")
        
        deposit_amount = st.number_input("Deposit/Withdraw Amount ($)", min_value=0.0, value=10000.0, step=1000.0)
        
        col_dep, col_with, col_reset = st.columns(3)
        
        with col_dep:
            if st.button("➕ Deposit", width='stretch'):
                new_balance = paper_engine.deposit(deposit_amount)
                st.success(f"Deposited ${deposit_amount:,.2f}. New cash: ${new_balance:,.2f}")
                st.rerun()
        
        with col_with:
            if st.button("➖ Withdraw", width='stretch'):
                try:
                    new_balance = paper_engine.withdraw(deposit_amount)
                    st.success(f"Withdrew ${deposit_amount:,.2f}. New cash: ${new_balance:,.2f}")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        
        with col_reset:
            if st.button("🔄 Reset Account", width='stretch'):
                paper_engine.reset_paper_account(starting_cash=100000)
                st.success("Paper account reset to $100,000")
                st.rerun()
    
    with col_right:
        st.subheader("Manual Trade")
        
        trade_ticker = st.text_input("Ticker Symbol", placeholder="AAPL").upper()
        trade_qty = st.number_input("Quantity", min_value=1, value=10)
        trade_action = st.radio("Action", ["BUY", "SELL"], horizontal=True)
        
        if st.button("Execute Paper Trade", type="primary"):
            if trade_ticker:
                try:
                    trade = paper_engine.execute_paper_trade(trade_ticker, trade_action, trade_qty)
                    st.success(f"Paper {trade_action}: {trade_qty} {trade_ticker} @ ${trade['price']:.2f}")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
            else:
                st.warning("Enter a ticker symbol")
    
    # Paper Positions
    st.divider()
    st.subheader("Paper Positions")
    
    if portfolio['positions']:
        pos_df = pd.DataFrame(portfolio['positions'])
        
        # Color P&L
        def color_pnl(val):
            color = '#00ff00' if val >= 0 else '#ff4444'
            return f'color: {color}'
        
        styled_df = pos_df.style.format({
            'avg_cost': '${:,.2f}',
            'current_price': '${:,.2f}',
            'market_value': '${:,.2f}',
            'cost_basis': '${:,.2f}',
            'pnl': '${:+,.2f}',
            'pnl_pct': '{:+.2f}%'
        }).applymap(color_pnl, subset=['pnl', 'pnl_pct'])
        
        st.dataframe(styled_df, width='stretch')
        
        # Pie chart for paper positions
        fig = px.pie(
            pos_df, 
            values='market_value', 
            names='ticker', 
            title='Paper Portfolio Allocation',
            hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        fig.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font_color='white'
        )
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("No paper positions. Use the form above to execute paper trades or run a paper rebalance.")
    
    # Paper Rebalance
    st.divider()
    st.subheader("Paper Rebalance (Strategy-Based)")
    
    if QUIVER_API_KEY:
        with st.spinner("Fetching signals for paper rebalance..."):
            strategy_signals, enabled_strategies = get_strategy_signals()
            
            if strategy_signals:
                all_tickers = []
                for strat_name, tickers in strategy_signals.items():
                    all_tickers.extend(tickers)
                unique_tickers = list(set(all_tickers))
                
                st.write(f"**Target tickers from enabled strategies:** {', '.join(unique_tickers[:15])}{'...' if len(unique_tickers) > 15 else ''}")
                
                alloc_pct = st.slider("Allocation % of portfolio", min_value=10, max_value=100, value=80, step=5)
                
                if st.button("🔄 Execute Paper Rebalance", type="secondary"):
                    with st.spinner("Executing paper rebalance..."):
                        trades = paper_engine.rebalance_paper(strategy_signals, enabled_strategies, allocation_pct=alloc_pct/100)
                        
                        if trades:
                            st.success(f"Paper rebalance complete! Executed {len(trades)} trades.")
                            trades_df = pd.DataFrame(trades)
                            st.dataframe(trades_df, width='stretch')
                        else:
                            st.info("No trades needed - portfolio already aligned.")
                        st.rerun()
            else:
                st.info("Enable strategies in the Strategies tab to get signals.")
    else:
        st.warning("Quiver API Key missing in .env")
    
    # Trade History
    st.divider()
    st.subheader("Paper Trade History")
    
    trade_history = paper_engine.get_trade_history(limit=20)
    if not trade_history.empty:
        st.dataframe(
            trade_history.style.format({
                'price': '${:,.2f}',
                'value': '${:,.2f}'
            }),
            width='stretch'
        )
    else:
        st.info("No paper trades yet.")

# ==================== BACKTESTING TAB ====================
with tab_backtest:
    st.markdown("### 📊 Strategy Backtesting")
    st.markdown("*Test your strategies on historical data to see how they would have performed.*")
    
    # Check if backtest engine is available
    BacktestEngineClass = get_backtest_engine()
    if BacktestEngineClass is None or not BacktestEngineClass.is_available():
        st.error("⚠️ Backtesting requires the `yfinance` package. Please install it:")
        st.code("pip install yfinance", language="bash")
        st.info("After installing, restart the dashboard with: `python -m streamlit run dashboard.py`")
        st.stop()
    
    # Backtest Configuration
    col_config1, col_config2 = st.columns(2)
    
    with col_config1:
        st.subheader("Backtest Settings")
        
        # Date range
        default_end = datetime.now()
        default_start = default_end - timedelta(days=365)
        
        backtest_start = st.date_input(
            "Start Date", 
            value=default_start,
            max_value=default_end - timedelta(days=30)
        )
        backtest_end = st.date_input(
            "End Date",
            value=default_end,
            max_value=default_end
        )
        
        initial_capital = st.number_input(
            "Initial Capital ($)",
            min_value=1000,
            max_value=10000000,
            value=100000,
            step=10000
        )
        
        rebalance_freq = st.selectbox(
            "Rebalance Frequency",
            options=['monthly', 'weekly', 'daily'],
            index=0
        )
        
        benchmark = st.selectbox(
            "Benchmark",
            options=['SPY', 'QQQ', 'IWM', 'DIA'],
            index=0
        )
    
    with col_config2:
        st.subheader("Select Tickers")
        
        # Option to use strategy signals or custom tickers
        ticker_source = st.radio(
            "Ticker Source",
            ["Use Strategy Signals", "Custom Tickers"],
            horizontal=True
        )
        
        if ticker_source == "Use Strategy Signals":
            if QUIVER_API_KEY:
                strategy_signals, enabled_strategies = get_strategy_signals()
                
                if strategy_signals:
                    # Show which strategies will be used
                    for strat_name, tickers in strategy_signals.items():
                        weight = next((s['weight'] for s in enabled_strategies if s['name'] == strat_name), 0)
                        st.write(f"**{strat_name}** ({weight}%): {', '.join(tickers[:5])}{'...' if len(tickers) > 5 else ''}")
                    
                    all_tickers = []
                    for tickers in strategy_signals.values():
                        all_tickers.extend(tickers)
                    backtest_tickers = list(set(all_tickers))
                else:
                    st.warning("No enabled strategies. Go to Strategies tab to enable them.")
                    backtest_tickers = []
            else:
                st.warning("Quiver API Key missing")
                backtest_tickers = []
        else:
            custom_tickers = st.text_area(
                "Enter tickers (comma-separated)",
                value="AAPL, MSFT, GOOGL, AMZN, NVDA",
                help="Enter stock symbols separated by commas"
            )
            backtest_tickers = [t.strip().upper() for t in custom_tickers.split(',') if t.strip()]
        
        st.write(f"**Total tickers:** {len(backtest_tickers)}")
    
    # Run Backtest Button
    st.divider()
    
    if st.button("🚀 Run Backtest", type="primary", disabled=len(backtest_tickers) == 0):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        def update_progress(progress, message):
            progress_bar.progress(progress)
            status_text.text(message)

        with st.spinner("Running backtest..."):
            # Use the same pricing fallback behavior as the system/backtests.
            # PRICE_SOURCE can be: yfinance | ib | auto
            engine = BacktestEngineClass(initial_capital=initial_capital, price_source=os.getenv("PRICE_SOURCE", "auto"))
            
            if ticker_source == "Use Strategy Signals" and strategy_signals:
                # Weighted backtest
                strategy_weights = {s['name']: s['weight'] for s in enabled_strategies}
                results = engine.run_weighted_backtest(
                    strategy_signals,
                    strategy_weights,
                    str(backtest_start),
                    str(backtest_end),
                    rebalance_freq,
                    progress_callback=update_progress
                )
            else:
                # Equal weight backtest
                results = engine.run_equal_weight_backtest(
                    backtest_tickers,
                    str(backtest_start),
                    str(backtest_end),
                    rebalance_freq,
                    progress_callback=update_progress
                )
            
            progress_bar.empty()
            status_text.empty()
            
            if 'error' in results:
                st.error(results['error'])
            else:
                # Store results in session state
                st.session_state['backtest_results'] = results
                st.session_state['backtest_engine'] = engine
                st.session_state['backtest_benchmark'] = benchmark
                st.success("Backtest complete!")
    
    # Display Results if available
    if 'backtest_results' in st.session_state:
        results = st.session_state['backtest_results']
        engine = st.session_state['backtest_engine']
        benchmark = st.session_state.get('backtest_benchmark', 'SPY')
        
        st.divider()
        st.subheader("📈 Backtest Results")
        
        # Key Metrics
        col1, col2, col3, col4 = st.columns(4)
        
        col1.metric(
            "Total Return",
            f"{results['total_return']:.1%}",
            delta=f"{results['total_return']:.1%}"
        )
        col2.metric(
            "CAGR",
            f"{results['cagr']:.1%}"
        )
        col3.metric(
            "Sharpe Ratio",
            f"{results['sharpe_ratio']:.2f}"
        )
        col4.metric(
            "Max Drawdown",
            f"{results['max_drawdown']:.1%}"
        )
        
        col5, col6, col7, col8 = st.columns(4)
        
        col5.metric(
            "Final Value",
            f"${results['final_value']:,.0f}"
        )
        col6.metric(
            "Volatility",
            f"{results['volatility']:.1%}"
        )
        col7.metric(
            "Sortino Ratio",
            f"{results['sortino_ratio']:.2f}"
        )
        col8.metric(
            "Win Rate",
            f"{results['win_rate']:.1%}"
        )
        
        # Equity Curve Chart
        st.subheader("Equity Curve")
        
        # Get benchmark comparison
        bench_comparison = engine.compare_to_benchmark(benchmark)
        
        fig = go.Figure()
        
        # Portfolio equity curve
        equity_df = results['equity_curve']
        fig.add_trace(go.Scatter(
            x=equity_df.index,
            y=equity_df['portfolio_value'],
            mode='lines',
            name='Portfolio',
            line=dict(color='#00d4aa', width=2)
        ))
        
        # Benchmark
        if 'benchmark_equity' in bench_comparison:
            bench_equity = bench_comparison['benchmark_equity']
            # Normalize to same starting value
            bench_normalized = bench_equity / bench_equity.iloc[0] * initial_capital
            fig.add_trace(go.Scatter(
                x=bench_normalized.index,
                y=bench_normalized.values,
                mode='lines',
                name=benchmark,
                line=dict(color='#ff6b6b', width=2, dash='dash')
            ))
        
        fig.update_layout(
            title='Portfolio vs Benchmark',
            xaxis_title='Date',
            yaxis_title='Portfolio Value ($)',
            template='plotly_dark',
            hovermode='x unified',
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
        )
        
        st.plotly_chart(fig, width='stretch')
        
        # Drawdown Chart
        st.subheader("Drawdown")
        
        fig_dd = go.Figure()
        
        dd_series = results['drawdown_series']
        fig_dd.add_trace(go.Scatter(
            x=dd_series.index,
            y=dd_series.values * 100,
            mode='lines',
            name='Drawdown',
            fill='tozeroy',
            line=dict(color='#ff6b6b', width=1),
            fillcolor='rgba(255, 107, 107, 0.3)'
        ))
        
        fig_dd.update_layout(
            title='Portfolio Drawdown',
            xaxis_title='Date',
            yaxis_title='Drawdown (%)',
            template='plotly_dark',
            hovermode='x unified'
        )
        
        st.plotly_chart(fig_dd, width='stretch')
        
        # Returns Distribution
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.subheader("Daily Returns Distribution")
            
            returns_series = results['returns_series']
            
            fig_hist = go.Figure()
            fig_hist.add_trace(go.Histogram(
                x=returns_series.values * 100,
                nbinsx=50,
                name='Daily Returns',
                marker_color='#00d4aa'
            ))
            
            fig_hist.update_layout(
                xaxis_title='Daily Return (%)',
                yaxis_title='Frequency',
                template='plotly_dark'
            )
            
            st.plotly_chart(fig_hist, width='stretch')
        
        with col_chart2:
            st.subheader("Monthly Returns Heatmap")
            
            # Calculate monthly returns
            monthly_returns = returns_series.resample('ME').apply(lambda x: (1 + x).prod() - 1)
            
            if len(monthly_returns) > 0:
                monthly_df = pd.DataFrame({
                    'Year': monthly_returns.index.year,
                    'Month': monthly_returns.index.month,
                    'Return': monthly_returns.values * 100
                })
                
                pivot = monthly_df.pivot(index='Year', columns='Month', values='Return')
                pivot.columns = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][:len(pivot.columns)]
                
                fig_heat = go.Figure(data=go.Heatmap(
                    z=pivot.values,
                    x=pivot.columns,
                    y=pivot.index,
                    colorscale='RdYlGn',
                    zmid=0,
                    text=[[f'{v:.1f}%' if not pd.isna(v) else '' for v in row] for row in pivot.values],
                    texttemplate='%{text}',
                    textfont={"size": 10},
                    hovertemplate='%{y} %{x}: %{z:.2f}%<extra></extra>'
                ))
                
                fig_heat.update_layout(
                    template='plotly_dark',
                    height=300
                )
                
                st.plotly_chart(fig_heat, width='stretch')
        
        # Benchmark Comparison
        if 'error' not in bench_comparison:
            st.subheader(f"Benchmark Comparison ({benchmark})")
            
            comp_col1, comp_col2, comp_col3, comp_col4 = st.columns(4)
            
            outperf = bench_comparison['outperformance']
            comp_col1.metric(
                "Outperformance",
                f"{outperf:+.1%}",
                delta=f"{outperf:+.1%}"
            )
            comp_col2.metric(
                "Alpha",
                f"{bench_comparison['alpha']:.2%}"
            )
            comp_col3.metric(
                "Beta",
                f"{bench_comparison['beta']:.2f}"
            )
            comp_col4.metric(
                "Information Ratio",
                f"{bench_comparison['information_ratio']:.2f}"
            )
            
            # Comparison table
            comparison_data = {
                'Metric': ['Total Return', 'CAGR', 'Volatility', 'Sharpe Ratio', 'Max Drawdown'],
                'Portfolio': [
                    f"{results['total_return']:.1%}",
                    f"{results['cagr']:.1%}",
                    f"{results['volatility']:.1%}",
                    f"{results['sharpe_ratio']:.2f}",
                    f"{results['max_drawdown']:.1%}"
                ],
                benchmark: [
                    f"{bench_comparison['benchmark_total_return']:.1%}",
                    f"{bench_comparison['benchmark_cagr']:.1%}",
                    f"{bench_comparison['benchmark_volatility']:.1%}",
                    f"{bench_comparison['benchmark_sharpe']:.2f}",
                    f"{bench_comparison['benchmark_max_drawdown']:.1%}"
                ]
            }
            
            st.dataframe(pd.DataFrame(comparison_data), width='stretch')
        
        # Tickers Used
        with st.expander("View Tickers Used in Backtest"):
            st.write(f"**{len(results['tickers'])} tickers:** {', '.join(results['tickers'])}")
            
            if 'weights' in results:
                weights_df = pd.DataFrame([
                    {'Ticker': t, 'Weight': f"{w:.2%}"} 
                    for t, w in results['weights'].items()
                ])
                st.dataframe(weights_df, width='stretch')

# ==================== STRATEGIES TAB ====================
with tab_strategies:
    st.subheader("Strategy Configuration")
    st.write("Enable/disable strategies and set allocation weights.")
    
    config = load_strategies_config()
    strategies = config.get('strategies', [])
    
    updated_strategies = []
    total_weight = 0
    
    for i, strat in enumerate(strategies):
        col1, col2, col3 = st.columns([3, 1, 2])
        
        with col1:
            enabled = st.checkbox(strat['name'], value=strat.get('enabled', False), key=f"strat_{i}")
        
        with col2:
            weight = st.number_input(
                "Weight %", 
                min_value=0, 
                max_value=100, 
                value=strat.get('weight', 0),
                key=f"weight_{i}",
                label_visibility="collapsed"
            )
        
        with col3:
            if enabled:
                total_weight += weight
                st.write(f"{weight}%")
        
        updated_strategies.append({
            **strat,
            'enabled': enabled,
            'weight': weight
        })
    
    if total_weight != 100 and total_weight > 0:
        st.warning(f"Total weight is {total_weight}%. Should equal 100% for proper allocation.")
    elif total_weight == 100:
        st.success("Weights properly allocated to 100%")
    
    if st.button("Save Strategy Configuration"):
        config['strategies'] = updated_strategies
        save_strategies_config(config)
        st.success("Configuration saved!")
        st.rerun()

# ==================== MARGINS TAB ====================
with tab_margins:
    if not ib_connected:
        st.warning("Connect to IBKR to view margin and balance details.")
    else:
        st.subheader("Margin & Balance Details")
        
        summary = get_account_summary(ib, selected_account)
        
        if summary:
            df_summary = pd.DataFrame(summary)
            
            st.markdown("### Account Overview")
            
            # Helper to get value for a tag, prioritizing USD if available
            def get_tag_value(df, tag):
                tag_data = df[df['tag'] == tag]
                if tag_data.empty:
                    return "N/A", ""
                
                # Look for USD first, then BASE, then anything else
                usd_row = tag_data[tag_data['currency'] == 'USD']
                if not usd_row.empty:
                    return float(usd_row['value'].iloc[0]), 'USD'
                
                base_row = tag_data[tag_data['currency'] == 'BASE']
                if not base_row.empty:
                    return float(base_row['value'].iloc[0]), base_row['currency'].iloc[0]
                
                return float(tag_data['value'].iloc[0]), tag_data['currency'].iloc[0]

            overview_cols = st.columns(4)
            overview_tags = [
                ('NetLiquidation', 'Net Liquidation'),
                ('TotalCashValue', 'Total Cash'),
                ('SettledCash', 'Settled Cash'),
                ('BuyingPower', 'Buying Power')
            ]
            
            for i, (tag, label) in enumerate(overview_tags):
                val, curr = get_tag_value(df_summary, tag)
                if val != "N/A":
                    overview_cols[i % 4].metric(label, f"{val:,.2f} {curr}")
                else:
                    overview_cols[i % 4].metric(label, "N/A")

            st.markdown("### Margin Requirements")
            margin_cols = st.columns(4)
            
            margin_tags = [
                ('InitMarginReq', 'Initial Margin'),
                ('MaintMarginReq', 'Maintenance Margin'),
                ('FullInitMarginReq', 'Full Initial Margin'),
                ('FullMaintMarginReq', 'Full Maint. Margin')
            ]
            
            for i, (tag, label) in enumerate(margin_tags):
                val, curr = get_tag_value(df_summary, tag)
                if val != "N/A":
                    margin_cols[i % 4].metric(label, f"{val:,.2f} {curr}")
                else:
                    margin_cols[i % 4].metric(label, "N/A")
            
            st.markdown("### Cash Balances by Currency")
            
            cash_rows = df_summary[df_summary['tag'].isin(['CashBalance', 'TotalCashBalance', 'TotalCashValue'])]
            
            if not cash_rows.empty:
                # We want to show individual currency balances
                # Filter out 'BASE' and focus on actual currencies for the breakdown
                currency_balances = {}
                for _, row in cash_rows.iterrows():
                    curr = row['currency']
                    if curr == 'BASE' or not curr: continue
                    val = float(row['value'])
                    if curr not in currency_balances:
                        currency_balances[curr] = val
                    else:
                        currency_balances[curr] = max(currency_balances[curr], val)
                
                # Also get the BASE total
                base_val, base_curr = get_tag_value(df_summary, 'TotalCashValue')
                
                if currency_balances or base_val != "N/A":
                    # Sort to show USD first
                    sorted_currencies = sorted(currency_balances.keys(), key=lambda x: (x != 'USD', x))
                    
                    # Create list of metrics to show: Base total first, then individual currencies
                    metrics = []
                    if base_val != "N/A":
                        metrics.append(("Total (Base)", base_val, base_curr))
                    for curr in sorted_currencies:
                        metrics.append((f"{curr} Balance", currency_balances[curr], curr))
                    
                    curr_cols = st.columns(min(len(metrics), 4))
                    for i, (label, val, curr) in enumerate(metrics):
                        curr_cols[i % 4].metric(label, f"{val:,.2f} {curr}")
            
            st.subheader("Account Details")
            
            # Combine key summary metrics with actual cash balances
            detailed_tags = [
                'NetLiquidation', 'EquityWithLoanValue', 'GrossPositionValue',
                'BuyingPower', 'ExcessLiquidity', 'AvailableFunds',
                'FullInitMarginReq', 'FullMaintMarginReq',
                'CashBalance', 'SettledCash', 'TotalCashValue'
            ]
            
            # Filter and format the data
            df_details = df_summary[df_summary['tag'].isin(detailed_tags)].copy()
            
            if not df_details.empty:
                # Convert values to float for sorting and formatting
                df_details['numeric_value'] = pd.to_numeric(df_details['value'], errors='coerce')
                
                # Sort: Important tags first, then by currency (BASE last, USD first)
                tag_order = {tag: i for i, tag in enumerate(detailed_tags)}
                df_details['tag_rank'] = df_details['tag'].map(tag_order)
                
                def currency_rank(curr):
                    if curr == 'USD': return 0
                    if curr == 'EUR': return 1
                    if curr == 'BASE': return 99
                    return 50
                
                df_details['curr_rank'] = df_details['currency'].apply(currency_rank)
                df_details = df_details.sort_values(['tag_rank', 'curr_rank'])
                
                # Format for display
                df_display = df_details[['tag', 'value', 'currency']].copy()
                df_display['value'] = df_display['value'].apply(lambda x: f"{float(x):,.2f}" if x and x != 'N/A' else x)
                
                st.dataframe(
                    df_display.rename(columns={'tag': 'Metric', 'value': 'Value', 'currency': 'Currency'}),
                    width='stretch',
                    height=400
                )
            else:
                st.info("No detailed account metrics found.")
        else:
            st.warning("Unable to fetch account summary.")

with tab_strategy_dashboard:
    st.subheader("Strategy Dashboard")
    st.caption("Embedded view of `STRATEGY_DASHBOARD.html` (local file).")

    dash_html = get_strategy_dashboard_html_cached()
    if not dash_html:
        st.warning("`STRATEGY_DASHBOARD.html` not found in the project root.")
    else:
        # Render inside an iframe-like sandbox; enable scrolling for long content.
        components.html(dash_html, height=1200, scrolling=True)
