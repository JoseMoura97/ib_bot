"""Final summary of Michael Burry backtest approaches."""

print("=" * 70)
print("MICHAEL BURRY - FINAL METHODOLOGY SUMMARY")
print("=" * 70)

print("""
APPROACH COMPARISON
-------------------

| Approach                  | CAGR   | Max DD  | Description                    |
|---------------------------|--------|---------|--------------------------------|
| Filter options (current)  | 20.76% | -38.62% | Stock positions only           |
| Options as exposure (new) | 15.26% | -50.92% | PUT=SHORT, CALL=LONG           |
| Include as stock (legacy) | 72.77% | -35.49% | WRONG: PUT treated as LONG     |
| Quiver reference          | 30.45% | -52.10% | Their methodology (unknown)    |


INSIGHTS
--------

1. LEGACY (72.77%) WAS WRONG:
   - Treated NVDA PUT as LONG NVDA
   - When NVDA went up 2000%, portfolio gained (wrong!)
   - Actual bet was SHORT NVDA, should have lost

2. OPTIONS AS EXPOSURE (15.26%) IS PROBABLY CLOSEST TO REALITY:
   - Burry is currently NET SHORT $829M (mostly NVDA, PLTR puts)
   - Being short tech during 2020-2024 bull market = losses
   - Max DD of -50.92% matches Quiver's -52.10%

3. FILTER OPTIONS (20.76%) IS A CONSERVATIVE MIDDLE GROUND:
   - Only looks at stock positions
   - Ignores option exposure entirely
   - More stable but misses Burry's actual strategy

4. QUIVER (30.45%) IS SOMEWHERE BETWEEN:
   - Quiver's methodology is proprietary
   - Could use delta-adjusted option exposure (~0.3-0.5x notional)
   - Could use a different lookback or rebalancing schedule
   - Max DD of -52.10% is similar to our options-as-exposure approach


RECOMMENDATION
--------------

For the dashboard, you have two options:

A) USE FILTER MODE (current default): 20.76% CAGR
   - Conservative, only uses stock positions
   - More stable equity curve
   - Doesn't capture Burry's full strategy

B) USE OPTIONS AS EXPOSURE MODE: 15.26% CAGR
   - More accurate reflection of actual exposure
   - Shows the reality of being net short during bull market
   - Matches Quiver's max drawdown better

To switch modes, set environment variable:
  SEC_13F_OPTIONS_MODE=filter       (default, stock only)
  SEC_13F_OPTIONS_MODE=as_exposure  (PUT=SHORT, CALL=LONG)
  SEC_13F_OPTIONS_MODE=include      (legacy, wrong - not recommended)


WHY WE CAN'T EXACTLY MATCH QUIVER
---------------------------------

1. Quiver's exact methodology is unknown (proprietary)
2. They may use delta-adjusted exposure instead of notional
3. Different price sources (Bloomberg vs Yahoo)
4. Different rebalancing timing (we use fixed schedule)
5. Possible different handling of edge cases

Bill Ackman shows our methodology IS correct:
  - Our CAGR: 17.63%
  - Quiver: 16.76%
  - Delta: <1% (excellent match!)

Ackman uses mostly stock, not options, so no filtering issues.
""")

# Reset to filter mode
import os
os.environ['SEC_13F_OPTIONS_MODE'] = 'filter'
