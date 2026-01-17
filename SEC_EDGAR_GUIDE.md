# SEC EDGAR Integration Guide

## Overview

This implementation allows you to fetch 13F filings **100% FREE** directly from the SEC, replacing Quiver's expensive 13F subscription tier.

### Cost Savings
- **Before**: Quiver Trader ($75/month) required for 13F data
- **After**: SEC EDGAR (FREE) + Quiver Hobbyist ($10/month)
- **Savings**: $65/month = **$780/year**

## What You Get

### 1. Direct SEC Access (`sec_edgar.py`)
- Fetch 13F filings from SEC EDGAR API
- Parse holdings data (CUSIP, shares, value)
- Support for 18+ major hedge funds pre-configured
- No rate limits with proper User-Agent

### 2. Hybrid Engine (`hybrid_data_engine.py`)
- **Automatically** uses SEC for 13F data (free)
- **Automatically** uses Quiver for congressional trading, lobbying, etc.
- Drop-in replacement for your existing code
- Compare data quality between sources

## Quick Start

### Installation

The implementation uses only standard Python libraries that you likely already have:

```bash
# Required (probably already installed):
pip install requests pandas beautifulsoup4 lxml
```

### Basic Usage

#### Option 1: Use Hybrid Engine (Recommended)

```python
from hybrid_data_engine import create_hybrid_engine
import os

# Initialize
engine = create_hybrid_engine(
    quiver_api_key=os.getenv("QUIVER_API_KEY"),
    sec_user_agent="YourName your.email@example.com"
)

# Get signals - automatically uses best source
burry_holdings = engine.get_signals("Michael Burry")  # Uses SEC (FREE)
congress_buys = engine.get_signals("Congress Buys")   # Uses Quiver

# Get combined portfolio
portfolio = engine.get_combined_portfolio(include_experimental=False)
```

#### Option 2: Use SEC EDGAR Directly

```python
from sec_edgar import SECEdgarEngine

# Initialize
engine = SECEdgarEngine("YourName your.email@example.com")

# Get holdings for specific funds
burry = engine.get_michael_burry_holdings()
ackman = engine.get_bill_ackman_holdings()
marks = engine.get_howard_marks_holdings()

# Or use generic method
buffett = engine.get_fund_holdings("Berkshire Hathaway")
```

### Testing

Run the test suite to verify everything works:

```powershell
# Set your Quiver API key (optional, for hybrid engine test)
$env:QUIVER_API_KEY = "your_key_here"

# Run tests
python test_sec_edgar.py
```

Expected output:
```
TEST SUMMARY
✓ PASS: CIK Lookup
✓ PASS: 13F Filing Retrieval
✓ PASS: Holdings Parsing
✓ PASS: Ticker Extraction
✓ PASS: Hybrid Engine

Result: 5/5 tests passed
🎉 All tests passed! SEC EDGAR integration is working.
```

## Supported Fund Managers

The following hedge fund managers are pre-configured:

| Fund Manager | Fund Name | Strategy Name |
|--------------|-----------|---------------|
| Michael Burry | Scion Asset Management | "Michael Burry" |
| Bill Ackman | Pershing Square Capital Management | "Bill Ackman" |
| Howard Marks | Oaktree Capital Management | "Howard Marks" |
| Warren Buffett | Berkshire Hathaway | "Warren Buffett" |
| Ray Dalio | Bridgewater Associates | "Ray Dalio" |
| David Tepper | Appaloosa Management | "David Tepper" |
| Seth Klarman | Baupost Group | "Seth Klarman" |
| David Einhorn | Greenlight Capital | "David Einhorn" |
| Dan Loeb | Third Point | "Dan Loeb" |
| Ken Griffin | Citadel | "Ken Griffin" |
| Steve Cohen | Point72 | "Steve Cohen" |

## Integration with Existing Code

### Update `quiver_signals.py`

Replace the existing code with the hybrid engine:

```python
from hybrid_data_engine import create_hybrid_engine
import os

class QuiverSignals:
    # ... existing strategy definitions ...
    
    def __init__(self, api_key):
        # Use hybrid engine instead of pure Quiver
        self.engine = create_hybrid_engine(
            quiver_api_key=api_key,
            sec_user_agent="IBBot contact@example.com"
        )
    
    def get_michael_burry_holdings(self):
        # Now uses SEC (free) instead of Quiver
        return self.engine.get_signals("Michael Burry")
    
    def get_bill_ackman_holdings(self):
        return self.engine.get_signals("Bill Ackman")
    
    def get_howard_marks_holdings(self):
        return self.engine.get_signals("Howard Marks")
    
    # ... rest of your methods stay the same ...
```

## Advanced Usage

### Compare Data Sources

```python
from hybrid_data_engine import create_hybrid_engine

engine = create_hybrid_engine(quiver_key, sec_user_agent)

# Compare SEC vs Quiver for Michael Burry
comparison = engine.compare_sources("Michael Burry")

print(f"SEC found: {comparison['sec_count']} tickers")
print(f"Quiver found: {comparison['quiver_count']} tickers")
print(f"Overlap: {comparison['overlap_percentage']:.1f}%")
print(f"SEC only: {comparison['sec_only']}")
print(f"Quiver only: {comparison['quiver_only']}")
```

### Add Custom Fund Managers

```python
from sec_edgar import SECEdgarClient

client = SECEdgarClient("YourName email@example.com")

# Search for any fund by name
cik = client.get_cik("Tiger Global Management")
if cik:
    holdings = client.get_fund_holdings("Tiger Global Management")
    print(f"Found {len(holdings)} holdings")
```

### Get Detailed Holdings Data

```python
from sec_edgar import SECEdgarClient

client = SECEdgarClient("YourName email@example.com")

# Get latest filing
filings = client.get_latest_13f_filings("Scion Asset Management", num_filings=1)

# Parse with full details
holdings_df = client.parse_13f_holdings(filings[0]['url'])

# holdings_df contains:
# - name: Company name
# - cusip: CUSIP identifier
# - shares: Number of shares
# - value: Position value (in dollars)
# - percentage: % of portfolio

print(holdings_df.head(10))
```

## How It Works

### SEC EDGAR API

1. **CIK Lookup**: Converts fund name to SEC's Central Index Key
2. **Filing Search**: Finds latest 13F-HR filings for the fund
3. **XML Parsing**: Extracts holdings from the information table XML
4. **Ticker Conversion**: Converts CUSIP numbers to ticker symbols

### Data Freshness

- **13F Filings**: Updated quarterly (45 days after quarter end)
- **Same as Quiver**: Quiver also sources from SEC 13F filings
- **Advantage**: You get the data as soon as SEC publishes (no middleman)

## Limitations & Notes

### CUSIP to Ticker Conversion

The current implementation uses a simple ticker lookup. For production use, consider:

1. **OpenFIGI API** (free, used in implementation)
2. **Build a CUSIP->Ticker database**
3. **Use a paid service** like Bloomberg or FactSet

### 13F Filing Lag

- Hedge funds file 13F reports **45 days after quarter end**
- This means holdings data is 1.5-3 months old
- **This is the same for Quiver** - they source from the same SEC filings

### Rate Limiting

- SEC allows **10 requests per second** with User-Agent
- Implementation uses conservative 5 req/sec
- No daily limits

## Troubleshooting

### "No tickers found"

This usually means CUSIP->ticker conversion failed. The holdings data is still parsed correctly, but ticker symbols couldn't be looked up.

**Solution**: Check if holdings_df has data in `parse_13f_holdings()`. If yes, implement a better CUSIP->ticker mapping.

### "CIK not found"

**Solution**: Search SEC manually for the fund name and add to `FUND_MANAGERS` dict in `sec_edgar.py`:

```python
FUND_MANAGERS = {
    "Your Fund Name": "1234567",  # Add CIK here
    # ...
}
```

### SEC Request Failures

**Solution**: Make sure you're providing a valid User-Agent with contact info:

```python
engine = SECEdgarEngine("YourName your.email@example.com")
```

## Migration Path

### Phase 1: Test (Current)
```bash
python test_sec_edgar.py  # Verify it works
```

### Phase 2: Parallel Run
- Keep Quiver for 13F data
- Run SEC in parallel to compare
- Use `compare_sources()` to validate

### Phase 3: Switch Over
- Update `quiver_signals.py` to use hybrid engine
- Downgrade Quiver subscription to Hobbyist ($10)
- Save $65/month

### Phase 4: Optimize (Optional)
- Build CUSIP->ticker database for better accuracy
- Add more hedge fund managers
- Implement custom filtering/weighting

## Support

If you encounter issues:

1. Check the test output: `python test_sec_edgar.py`
2. Enable debug logging:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```
3. Compare with Quiver data using `compare_sources()`

## Next Steps

1. ✅ Run tests: `python test_sec_edgar.py`
2. ✅ Compare data quality with your existing Quiver data
3. ✅ Update your main code to use `hybrid_data_engine`
4. ✅ Monitor for a few days to ensure stability
5. ✅ Downgrade Quiver subscription to save $780/year

---

**Questions?** Check the code comments in `sec_edgar.py` and `hybrid_data_engine.py` for detailed documentation.
