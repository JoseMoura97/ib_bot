"""
Instrument classifier for backtest ingest pipelines.

Purpose
-------
Decide whether a row from a 13F filing or a Congressional disclosure represents
a security we can price as a US-listed equity. Non-equity instruments (mutual
funds, bond funds, options, warrants, units, rights, certain ADR variants) are
the root cause of "missing ticker segments" in our backtests because the
downstream pricer only knows how to resolve `secType="STK"` contracts.

Why a single module
-------------------
The same classification logic is needed in:
- sec_edgar.py (13F parsing — has TitleOfClass + PutCall + Name)
- quiver_engine.py (Congressional / lobbying / contract data — usually only
  has a Ticker string and sometimes an asset-type column)
- backtest_engine.py (IB fetcher — needs to know whether to construct a Stock,
  MutualFund, or Option contract)

Keeping the rules in one place prevents drift and makes the regression suite
trivial to write.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SecurityType(str, Enum):
    COMMON_STOCK = "common_stock"
    PREFERRED = "preferred"
    ETF = "etf"
    MUTUAL_FUND = "mutual_fund"
    BOND = "bond"
    OPTION = "option"
    WARRANT = "warrant"
    RIGHT = "right"
    UNIT = "unit"
    NOTE = "note"
    UNKNOWN = "unknown"


# Default admissible types for equity backtests. Override per-strategy if needed.
DEFAULT_ADMISSIBLE = frozenset({
    SecurityType.COMMON_STOCK,
    SecurityType.ETF,
})


# --- pattern dictionaries -------------------------------------------------

# TitleOfClass tokens. We match on word boundaries / contains.
# Order matters: more specific patterns first.
_TITLE_PATTERNS = [
    (re.compile(r"\bWARRANT\b|\bWTS?\b|\bWT\b", re.I), SecurityType.WARRANT),
    (re.compile(r"\bRIGHTS?\b|\bRTS?\b", re.I), SecurityType.RIGHT),
    (re.compile(r"\bUNITS?\b|\bUNT\b", re.I), SecurityType.UNIT),
    (re.compile(r"\bPREF(ERRED)?\b|\bPFD\b", re.I), SecurityType.PREFERRED),
    (re.compile(r"\bNOTE[S]?\b|\bDEBENTURE", re.I), SecurityType.NOTE),
    (re.compile(r"\bBOND[S]?\b", re.I), SecurityType.BOND),
    (re.compile(r"\bCALL\b|\bPUT\b", re.I), SecurityType.OPTION),
    (re.compile(r"\bMUTUAL FUND\b|\bMUT FD\b", re.I), SecurityType.MUTUAL_FUND),
    (re.compile(r"\bETF\b|\bETN\b", re.I), SecurityType.ETF),
    (re.compile(r"\bCOM\b|\bCOMMON\b|\bORD\b|\bCL\s*[A-Z]\b|\bCLASS\s*[A-Z]\b|\bSHS\b|\bSHARES\b|\bADR\b|\bADS\b", re.I), SecurityType.COMMON_STOCK),
]

# Name patterns that strongly imply non-equity instruments (used when
# TitleOfClass is empty — common for Congressional data).
_NAME_PATTERNS = [
    (re.compile(r"\bMUTUAL FUND\b|\bMONEY MARKET\b|\bMONEY MKT\b", re.I), SecurityType.MUTUAL_FUND),
    (re.compile(r"\bBOND FUND\b|\bFIXED INCOME FUND\b", re.I), SecurityType.BOND),
    (re.compile(r"\bTREASURY\b.*\b(NOTE|BILL|BOND)\b", re.I), SecurityType.NOTE),
    # Plain ETF detection is risky from name alone; prefer ticker form.
]

# Tickers that follow well-known mutual-fund conventions.
# US open-end mutual funds: 5 letters, ending in 'X' (e.g., VFIAX, FXAIX, SWPPX).
# Exception list to avoid false positives on legitimate stocks ending in X.
_MUTUAL_FUND_TICKER_RE = re.compile(r"^[A-Z]{4}X$")
_KNOWN_STOCK_X_SUFFIX = frozenset({
    "CTRX", "ESRX", "RSTX", "FOXX", "NETX", "XRX",  # legacy/edge cases
})

# Tickers that clearly aren't a single common stock.
_OBVIOUS_NON_EQUITY_TICKER = re.compile(
    r"(?:^N/A$|^NONE$|^CASH$|^FUND$|^MM$|^MMKT$|^USD$)",
    re.I,
)


@dataclass(frozen=True)
class Classification:
    security_type: SecurityType
    confidence: float  # 0.0 - 1.0
    reason: str

    @property
    def is_priceable_equity(self) -> bool:
        return self.security_type in DEFAULT_ADMISSIBLE


def classify(
    *,
    ticker: Optional[str] = None,
    name: Optional[str] = None,
    title_of_class: Optional[str] = None,
    put_call: Optional[str] = None,
    asset_type_hint: Optional[str] = None,
) -> Classification:
    """
    Classify a security row. All inputs optional, but at least one should be
    provided. Returns a `Classification` indicating type, confidence, and the
    rule that fired.

    Precedence (most specific first):
      1. explicit put_call (PUT/CALL)        -> OPTION
      2. asset_type_hint string match        -> direct mapping
      3. title_of_class pattern              -> COMMON / PREF / WARRANT / etc.
      4. name patterns                       -> MUTUAL_FUND / BOND
      5. ticker form                         -> MUTUAL_FUND (xxxxX)
      6. fallback                            -> COMMON_STOCK if ticker looks
                                                 stock-like, else UNKNOWN
    """
    # 1) explicit put_call
    if put_call:
        pc = str(put_call).strip().upper()
        if pc in {"PUT", "CALL"}:
            return Classification(SecurityType.OPTION, 1.0, f"put_call={pc}")

    # 2) explicit asset_type_hint
    if asset_type_hint:
        h = str(asset_type_hint).strip().upper()
        if "OPTION" in h:
            return Classification(SecurityType.OPTION, 0.95, f"hint={h}")
        if "MUTUAL" in h or "MMKT" in h or "MMF" in h or "MONEY MARKET" in h:
            return Classification(SecurityType.MUTUAL_FUND, 0.95, f"hint={h}")
        if "ETF" in h or "ETN" in h:
            return Classification(SecurityType.ETF, 0.95, f"hint={h}")
        if "BOND" in h or "FIXED INCOME" in h or "TREASURY" in h:
            return Classification(SecurityType.BOND, 0.9, f"hint={h}")
        if "WARRANT" in h:
            return Classification(SecurityType.WARRANT, 0.95, f"hint={h}")
        if "PREF" in h:
            return Classification(SecurityType.PREFERRED, 0.95, f"hint={h}")
        if "STOCK" in h or "EQUIT" in h or "COMMON" in h or "ADR" in h:
            return Classification(SecurityType.COMMON_STOCK, 0.85, f"hint={h}")

    # 3) TitleOfClass (13F)
    if title_of_class:
        title = str(title_of_class).strip()
        for pat, sec_type in _TITLE_PATTERNS:
            if pat.search(title):
                return Classification(sec_type, 0.9, f"title:{pat.pattern[:20]}")

    # 4) Name patterns
    if name:
        nm = str(name).strip()
        for pat, sec_type in _NAME_PATTERNS:
            if pat.search(nm):
                return Classification(sec_type, 0.8, f"name:{pat.pattern[:20]}")

    # 5) Ticker form
    if ticker:
        t = str(ticker).strip().upper()
        if _OBVIOUS_NON_EQUITY_TICKER.match(t):
            return Classification(SecurityType.UNKNOWN, 0.9, "obvious_non_equity")
        if _MUTUAL_FUND_TICKER_RE.match(t) and t not in _KNOWN_STOCK_X_SUFFIX:
            return Classification(SecurityType.MUTUAL_FUND, 0.75, "ticker:5L-X")
        # Stock-like: 1-5 letters, optionally with -A/-B class suffix
        if re.fullmatch(r"[A-Z]{1,5}(?:-[A-Z]{1,2})?", t):
            return Classification(SecurityType.COMMON_STOCK, 0.6, "ticker:stock-like")

    return Classification(SecurityType.UNKNOWN, 0.0, "no-signal")


def is_priceable_as_stk(c: Classification) -> bool:
    """True when the default IB Stock(secType=STK) contract will resolve."""
    return c.security_type in {SecurityType.COMMON_STOCK, SecurityType.ETF}


def ib_sec_type(c: Classification) -> Optional[str]:
    """
    Map to IB `secType` for contract construction. Returns None if the type
    is not priceable through ib_insync's main contract families.
    """
    if c.security_type in {SecurityType.COMMON_STOCK, SecurityType.ETF}:
        return "STK"
    if c.security_type == SecurityType.MUTUAL_FUND:
        return "MF"
    if c.security_type == SecurityType.OPTION:
        return "OPT"
    if c.security_type == SecurityType.BOND or c.security_type == SecurityType.NOTE:
        return "BOND"
    return None
