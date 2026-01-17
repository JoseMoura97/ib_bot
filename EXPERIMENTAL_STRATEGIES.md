# Experimental Strategies Added

## Overview
Added 11 new **experimental strategies** while marking the original 5 as **core strategies**. All experimental strategies are disabled by default and can be enabled individually for testing.

---

## Core Strategies (5 Total - Currently Active)

These are production-ready strategies currently running with allocated weights:

| Strategy | Weight | Description |
|----------|--------|-------------|
| **Congress Buys** | 25% | Tracks recent stock purchases by members of Congress, weighted by reported purchase size with weekly rebalancing. |
| **Dan Meuser** | 20% | Mirrors the portfolio of Rep. Dan Meuser (and family), rebalanced when new trades or annual reports are reported. |
| **Sector Weighted DC Insider** | 20% | Tracks aggregated insider trading activity weighted by sector allocation with weekly rebalancing. |
| **Michael Burry** | 20% | Mirrors Scion Asset Management's portfolio using 13F filings, rebalanced when new filings are reported. |
| **Lobbying Spending Growth** | 15% | Invests in companies with growing lobbying budgets, identifying firms increasing political influence. |

**Total Weight: 100%**

---

## Experimental Strategies (11 Total - Available for Testing)

These strategies are available for experimentation and can be enabled individually:

### Congressional Trading Strategies

#### 1. Transportation and Infra. Committee (House)
- **CAGR:** 33.58% | **1Y Return:** 54.55%
- **Description:** Tracks stocks purchased by current/past members of the U.S. House's Transportation and Infrastructure Committee (or their family). Weighted based on reported purchase size, with weekly rebalancing.
- **Status:** 🧪 Experimental (Disabled)

#### 2. U.S. House Long-Short
- **CAGR:** 31.80% | **1Y Return:** 33.79%
- **Description:** Tracks stocks purchased or sold by U.S. House members (or family). Long position in purchases, short position in sales. Employs leverage with 130% long exposure and 30% short exposure, with weekly rebalancing.
- **Status:** 🧪 Experimental (Disabled)

#### 3. Donald Beyer
- **CAGR:** 20.17% | **1Y Return:** 22.07%
- **Description:** Mirrors the portfolio of Rep. Don Beyer (and family). Rebalanced when new trades or annual reports are reported.
- **Status:** 🧪 Experimental (Disabled)

#### 4. Josh Gottheimer
- **CAGR:** 21.62% | **1Y Return:** 14.36%
- **Description:** Mirrors the portfolio of Rep. Josh Gottheimer (and family). Rebalanced when new trades or annual reports are reported.
- **Status:** 🧪 Experimental (Disabled)

#### 5. Nancy Pelosi
- **CAGR:** 21.23% | **1Y Return:** 16.59%
- **Description:** Mirrors the portfolio of Rep. Nancy Pelosi (and family). Rebalanced when new trades or annual reports are reported.
- **Status:** 🧪 Experimental (Disabled)

#### 6. Sheldon Whitehouse
- **CAGR:** 18.51% | **1Y Return:** 24.89%
- **Description:** Mirrors the portfolio of Senator Sheldon Whitehouse (and family). Rebalanced when new trades or annual reports are reported.
- **Status:** 🧪 Experimental (Disabled)

### Government & Lobbying Strategies

#### 7. Top Gov Contract Recipients
- **CAGR:** 19.16% | **1Y Return:** 16.02%
- **Description:** Selects top 20 government contract recipients, weighted by contract values. Uses exponential moving average to favor recent contracts while weighing historical ones. Rebalanced monthly.
- **Status:** 🧪 Experimental (Disabled)

#### 8. Top Lobbying Spenders
- **CAGR:** 16.73% | **1Y Return:** 23.21%
- **Description:** Equal-weighted position in 10 publicly-traded companies with most lobbying spending over the last quarter. Rebalanced monthly.
- **Status:** 🧪 Experimental (Disabled)

### Hedge Fund Strategies

#### 9. Howard Marks
- **CAGR:** 15.63% | **1Y Return:** 39.39%
- **Description:** Mirrors Howard Marks's Oaktree Capital Management portfolio using 13F filings. Rebalanced when new filings are reported.
- **Status:** 🧪 Experimental (Disabled)

#### 10. Bill Ackman
- **CAGR:** 16.98% | **1Y Return:** 10.02%
- **Description:** Mirrors Bill Ackman's Pershing Square Capital Management portfolio using 13F filings. Rebalanced when new filings are reported.
- **Status:** 🧪 Experimental (Disabled)

#### 11. Wall Street Conviction
- **CAGR:** 18.00% | **1Y Return:** 17.49%
- **Description:** Uses 13F filings for institutions with $100M+ holdings to find each fund's highest conviction stock in the S&P500. Conviction measured as portfolio allocation minus S&P500 allocation. Equal-weighted positions, rebalanced quarterly 47 days after quarter end.
- **Status:** 🧪 Experimental (Disabled)

---

## Usage

### Accessing Strategy Information

```python
from quiver_signals import QuiverSignals

# Get all available strategies with metadata
all_strategies = QuiverSignals.get_all_strategies()

# Get info for a specific strategy
strategy_info = QuiverSignals.get_strategy_info("Nancy Pelosi")
print(strategy_info['description'])
print(strategy_info['category'])  # 'core' or 'experimental'
```

### Using Experimental Strategies

```python
from quiver_signals import QuiverSignals
import os

api_key = os.getenv('QUIVER_API_KEY')
qs = QuiverSignals(api_key)

# Get signals from specific experimental strategies
pelosi_signals = qs.get_nancy_pelosi_trades()
beyer_signals = qs.get_donald_beyer_trades()
gov_contracts = qs.get_gov_contract_recipients()
conviction = qs.get_wall_street_conviction()

# Get combined portfolio (core strategies only)
core_portfolio = qs.get_combined_portfolio()

# Get combined portfolio including experimental strategies
full_portfolio = qs.get_combined_portfolio(include_experimental=True)
```

### Enabling Experimental Strategies

Edit `strategies_config.json`:

```json
{
  "id": "nancy_pelosi",
  "name": "Nancy Pelosi",
  "category": "experimental",
  "enabled": true,      // Change to true
  "weight": 10,         // Set desired weight
  "description": "...",
  "metrics": {...}
}
```

**Note:** When enabling experimental strategies, adjust weights so all enabled strategies total 100%.

---

## Files Modified

1. **`quiver_signals.py`**
   - Added `CORE_STRATEGIES` and `EXPERIMENTAL_STRATEGIES` dictionaries with metadata
   - Added 11 new methods for experimental strategies
   - Added `get_strategy_info()` and `get_all_strategies()` class methods
   - Updated `get_combined_portfolio()` to support `include_experimental` parameter

2. **`quiver_engine.py`**
   - Added metadata for 11 experimental strategies
   - Marked core strategies with `category: "core"`
   - Marked experimental strategies with `category: "experimental"`

3. **`strategies_config.json`**
   - Added `category` field to all strategies
   - Added `description` field to all strategies
   - Added 11 experimental strategy entries (all disabled by default)
   - Added `metrics` field with CAGR and 1Y returns for experimental strategies

---

## Performance Comparison

### Top Performing Experimental Strategies (by 1Y Return)

| Rank | Strategy | 1Y Return | CAGR |
|------|----------|-----------|------|
| 1 | Transportation Committee | **54.55%** | 33.58% |
| 2 | Howard Marks | **39.39%** | 15.63% |
| 3 | U.S. House Long-Short | **33.79%** | 31.80% |
| 4 | Sheldon Whitehouse | **24.89%** | 18.51% |
| 5 | Top Lobbying Spenders | **23.21%** | 16.73% |

### Top Performing by CAGR

| Rank | Strategy | CAGR | 1Y Return |
|------|----------|------|-----------|
| 1 | Transportation Committee | **33.58%** | 54.55% |
| 2 | U.S. House Long-Short | **31.80%** | 33.79% |
| 3 | Josh Gottheimer | **21.62%** | 14.36% |
| 4 | Nancy Pelosi | **21.23%** | 16.59% |
| 5 | Donald Beyer | **20.17%** | 22.07% |

---

## Testing Recommendations

### Phase 1: Individual Strategy Testing
1. Enable one experimental strategy at a time
2. Allocate 5-10% weight for testing
3. Monitor for 2-4 weeks
4. Compare against core strategies

### Phase 2: Category Testing
1. Test similar strategies together:
   - Congressional traders (Pelosi, Beyer, Gottheimer, etc.)
   - Hedge funds (Marks, Ackman, Burry)
   - Government-related (Contracts, Lobbying)

### Phase 3: Combined Testing
1. Create blended portfolios with multiple experimental strategies
2. Monitor correlation with core strategies
3. Adjust weights based on performance

---

## Risk Considerations

⚠️ **Important Notes:**

1. **Experimental Status:** These strategies have not been tested in your production environment
2. **Higher Volatility:** Some strategies (especially long-short) may have higher volatility
3. **Correlation:** Many congressional strategies may be highly correlated
4. **Data Availability:** Some strategies may have limited or delayed data
5. **Leverage:** The House Long-Short strategy uses 130% long / 30% short leverage

---

## Next Steps

1. ✅ Review this documentation
2. ✅ Test API connectivity for experimental strategies:
   ```bash
   python test_api_endpoints.py "Nancy Pelosi"
   python test_api_endpoints.py "Wall Street Conviction"
   ```
3. ✅ Enable 1-2 experimental strategies with small weights (5-10%)
4. ✅ Monitor performance in paper trading for 2-4 weeks
5. ✅ Gradually adjust allocation based on results
6. ✅ Update `strategies_config.json` with your final allocation

---

## Questions?

For implementation details, see:
- `quiver_signals.py` - High-level strategy interface
- `quiver_engine.py` - Strategy metadata and signal fetching logic
- `strategies_config.json` - Strategy configuration and weights
- `TEST_README.md` - Testing documentation
