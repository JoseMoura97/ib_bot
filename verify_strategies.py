#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Quick verification script for strategy changes."""

import sys

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from quiver_signals import QuiverSignals

# Use ASCII-safe symbols for Windows
CHECK = '[OK]'
EXPERIMENT = '[EXP]'

# Get all strategies
all_strategies = QuiverSignals.get_all_strategies()

# Count by category
core_count = sum(1 for s in all_strategies.values() if s.get('category') == 'core')
experimental_count = sum(1 for s in all_strategies.values() if s.get('category') == 'experimental')

print("=" * 70)
print("STRATEGY VERIFICATION")
print("=" * 70)
print(f"\nTotal Strategies: {len(all_strategies)}")
print(f"  Core: {core_count}")
print(f"  Experimental: {experimental_count}")

print("\n" + "=" * 70)
print("CORE STRATEGIES")
print("=" * 70)
for name, info in all_strategies.items():
    if info.get('category') == 'core':
        desc = info.get('description', 'N/A')[:60]
        print(f"  {CHECK} {name}")
        print(f"    {desc}...")

print("\n" + "=" * 70)
print("EXPERIMENTAL STRATEGIES")
print("=" * 70)
for name, info in all_strategies.items():
    if info.get('category') == 'experimental':
        cagr = info.get('cagr', 'N/A')
        return_1y = info.get('return_1y', 'N/A')
        print(f"  {EXPERIMENT} {name}")
        print(f"    CAGR: {cagr} | 1Y: {return_1y}")

print("\n" + "=" * 70)
print("TEST STRATEGY INFO RETRIEVAL")
print("=" * 70)

test_strategies = ["Nancy Pelosi", "Michael Burry", "Wall Street Conviction"]
for strat_name in test_strategies:
    info = QuiverSignals.get_strategy_info(strat_name)
    if info:
        print(f"\n{CHECK} {strat_name}:")
        print(f"  Category: {info.get('category')}")
        print(f"  Description: {info.get('description', 'N/A')[:80]}...")
    else:
        print(f"\n[X] {strat_name}: Not found")

print("\n" + "=" * 70)
print("VERIFICATION COMPLETE")
print("=" * 70)
