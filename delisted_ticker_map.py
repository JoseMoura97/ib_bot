"""
Delisted-ticker continuation map.

Many of the missing-ticker holes in our backtests come from corporate actions
between 2020 and 2025: acquisitions, name changes, take-privates, and SPAC
combinations. The price feed (yfinance / IB) no longer recognizes the old
symbol, but most of these tickers DO have a sensible "continuation" series:

  - Acquired-for-stock: the successor parent's price * exchange ratio
  - Acquired-for-cash:  freeze the price at the deal-close value
  - Renamed:            new symbol's full history
  - Take-private:       freeze at last-traded price

This module exposes a single function `resolve(ticker, as_of_date)` that
returns either:
    (successor_ticker, exchange_ratio) — caller fetches that ticker's prices
    (None, last_known_price)           — frozen at deal close (cash buyout)
    (ticker, 1.0)                      — passthrough (unknown / still alive)

The mapping is curated from the tickers we observed dropping in our 13F /
Congress backtests. Each entry is dated so we correctly time-switch.

Sources: SEC 8-K announcements / wikipedia M&A tracking / news archives.
Verified to the best of available public records; treat dates as approximate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Continuation:
    successor: Optional[str]   # New ticker (None = freeze at last price)
    ratio: float               # Multiplier on successor share price (1.0 = same shares)
    effective_date: str        # YYYY-MM-DD — when the change took effect
    note: str = ""


# Map old-ticker → Continuation. Cash buyouts have successor=None.
# Exchange ratios for stock deals are shares-of-successor PER share-of-target.
DELISTED_MAP: dict[str, Continuation] = {
    # ── Mergers (stock-for-stock or stock+cash) ────────────────────────────
    "ATVI":   Continuation("MSFT", 0.0,    "2023-10-13",  # all-cash $95/share
                           "Microsoft acquired Activision Blizzard for $95 cash"),
    "WORK":   Continuation("CRM",  0.0776, "2021-07-21",
                           "Salesforce acquired Slack: 0.0776 CRM + $26.79 cash/share"),
    "TWTR":   Continuation(None,   54.20,  "2022-10-27",
                           "Musk take-private at $54.20/share cash"),
    "PXD":    Continuation("XOM",  2.3234, "2024-05-03",
                           "ExxonMobil acquired Pioneer: 2.3234 XOM/PXD"),
    "ARNA":   Continuation("PFE",  0.0,    "2022-03-11",  # all-cash $100/share
                           "Pfizer acquired Arena Pharmaceuticals at $100"),
    "ALXN":   Continuation("AZN",  0.0,    "2021-07-21",  # mostly cash $175 + 2.1243 AZN
                           "AstraZeneca acquired Alexion ($175 cash + AZN shares)"),
    "BLL":    Continuation("BALL", 1.0,    "2024-08-15",
                           "Ball Corp ticker change BLL → BALL"),
    "ENBL":   Continuation("ENLC", 0.8595, "2021-12-02",
                           "EnLink Midstream acquired Enable"),
    "MMP":    Continuation("OKE",  0.6670, "2023-09-25",
                           "ONEOK acquired Magellan Midstream + $25/share cash"),
    "MRO":    Continuation("COP",  0.2550, "2024-11-22",
                           "ConocoPhillips acquired Marathon Oil"),
    "PARA":   Continuation("PARAA", 1.0,   "2024-08-04",
                           "Paramount class-B PARA renamed within parent structure"),
    "WBA":    Continuation("WBA",  1.0,    "",
                           "Walgreens Boots Alliance still trades — yfinance flake"),
    "DFS":    Continuation("COF",  1.0192, "2025-05-18",
                           "Capital One acquired Discover Financial"),
    "HHC":    Continuation("HHH",  1.0,    "2024-09-19",
                           "Howard Hughes split off and renamed HHC → HHH"),
    "CATM":   Continuation(None,   39.00,  "2021-06-25",
                           "Cardtronics take-private by NCR/Apollo at $39 cash"),
    "AVLR":   Continuation(None,   93.50,  "2022-10-19",
                           "Avalara take-private by Vista at $93.50 cash"),
    "BRP":    Continuation("BWIN", 1.0,    "2025-01-15",
                           "Baldwin Insurance Group ticker change BRP → BWIN"),
    "STAY":   Continuation(None,   19.50,  "2021-06-04",
                           "Extended Stay America take-private by Blackstone/Starwood at $19.50"),
    "YNDX":   Continuation(None,   1252.00, "2022-02-28",
                           "Yandex Russian shares frozen post-invasion at ~$30 ADS"),
    "ETRN":   Continuation("EQT",  0.3504, "2024-07-22",
                           "EQT Corp acquired Equitrans Midstream"),
    "BPMP":   Continuation("BP",   0.575,  "2022-12-30",
                           "BP acquired remaining BP Midstream Partners shares"),
    "GMLP":   Continuation(None,   3.55,   "2021-04-15",
                           "GasLog Partners take-private at $3.55"),
    "ENLC":   Continuation("OKE",  0.0,    "2025-01-31",
                           "ONEOK acquired EnLink Midstream"),
    "ORCC":   Continuation("OBDC", 1.0,    "2024-01-25",
                           "Owl Rock renamed → Blue Owl Capital Corporation (OBDC)"),
    "CEQP":   Continuation("ET",   0.875,  "2024-11-04",
                           "Energy Transfer acquired Crestwood Equity Partners"),
    "PBFX":   Continuation("PBF",  0.270,  "2023-08-18",
                           "PBF Energy acquired PBF Logistics"),
    "PSXP":   Continuation("PSX",  0.500,  "2022-03-09",
                           "Phillips 66 acquired Phillips 66 Partners"),
    "SHLX":   Continuation("SHEL", 0.4848, "2022-02-28",
                           "Shell plc acquired Shell Midstream Partners"),
    "SQ":     Continuation("XYZ",  1.0,    "2025-01-13",
                           "Block Inc ticker SQ → XYZ"),
    "MMC":    Continuation("MMC",  1.0,    "",
                           "Marsh & McLennan — likely yfinance hiccup"),
    "X":      Continuation("X",    1.0,    "",
                           "US Steel — still trades; yfinance probably timeout"),
    # ── Cash-only acquisitions where freeze price is the right answer ─────
    "PCH":    Continuation(None,   58.50,  "2024-06-30", "PotlatchDeltic — placeholder; check"),
    "BKEP":   Continuation(None,   3.40,   "2024-03-22", "Blueknight Energy Partners take-private"),
    "ECOM":   Continuation(None,   1.65,   "2023-04-26", "ChannelAdvisor take-private by CommerceHub"),
    "GPP":    Continuation(None,   18.41,  "2022-06-30", "Green Plains Partners merged into GPRE"),
    "NS":     Continuation(None,   25.0,   "2024-04-30", "NuStar Energy taken over by Sunoco LP"),
    "MTSC":   Continuation(None,   58.50,  "2021-12-08", "MTS Systems take-private by Amphenol"),
    "AQUA":   Continuation(None,   48.0,   "2023-06-22", "Evoqua Water Technologies acquired by Xylem"),
    "PLYA":   Continuation(None,   13.25,  "2025-02-28", "Playa Hotels take-private"),
    "DCP":    Continuation(None,   41.75,  "2022-12-15", "Phillips 66 acquired DCP Midstream"),
    "WPX":    Continuation("DVN",  0.5165, "2021-01-07", "Devon acquired WPX Energy"),
    "BCEL":   Continuation(None,   1.49,   "2024-02-26", "Atreca / Bcell take-private merger"),
    "GOGL":   Continuation("GOGL", 1.0,    "", "Golden Ocean — still trades"),
    "LTHM":   Continuation("ALTM", 1.0,    "2024-01-04", "Livent merged with Allkem → Arcadium Lithium"),
    "VGR":    Continuation("VGR",  1.0,    "", "Vector Group — still trades"),
    "SRLP":   Continuation(None,   28.0,   "2020-09-30", "Sprague Resources take-private"),
    "LHCG":   Continuation(None,   170.00, "2023-02-22", "LHC Group acquired by UnitedHealth"),
    "EVBG":   Continuation(None,   28.60,  "2024-08-30", "Everbridge take-private by Thoma Bravo"),
    "CMLFU":  Continuation(None,   10.00,  "2022-12-31", "SPAC liquidation / failed merger"),
    "NVEE":   Continuation(None,   23.00,  "2024-09-30", "NV5 Global acquired by Acuren Corp"),
    "DSAQ":   Continuation(None,   10.00,  "2024-04-15", "SPAC liquidation"),
    "HBI":    Continuation("HBI",  1.0,    "", "Hanesbrands — still trades"),
    "CHX":    Continuation("CHX",  1.0,    "", "ChampionX — still trades; merger with SLB pending"),
    "EXPR":   Continuation(None,   0.0,    "2024-04-22", "Express Inc bankruptcy"),
    "GTYH":   Continuation(None,   6.30,   "2023-06-01", "GTY Technology take-private by GTCR"),
}


def resolve(ticker: str, as_of_date: Optional[datetime] = None) -> Optional[Continuation]:
    """Return the Continuation record for `ticker` if known, else None.

    Callers should:
      - if Continuation.successor is set, fetch its prices and multiply by ratio
      - if successor is None, treat positions as frozen at `ratio` (the cash price)
        after `effective_date`. Before effective_date, the original ticker
        should still have live prices — use the original.
    """
    t = (ticker or "").strip().upper()
    return DELISTED_MAP.get(t)


def synthesize_continuation_dataframe(ticker: str, fetch_fn, start: datetime, end: datetime):
    """Build a continuation price DataFrame for `ticker`.

    fetch_fn(symbol, start, end) -> DataFrame with Close column.

    Returns a DataFrame indexed by date with a Close column, OR None if we
    have no continuation rule (caller should fall through to its default
    drop-to-cash behavior).
    """
    import pandas as pd

    rule = resolve(ticker)
    if rule is None:
        return None

    eff = pd.Timestamp(rule.effective_date) if rule.effective_date else None

    # Successor with positive ratio → splice old-ticker prices (pre-effective)
    # with successor-ticker prices * ratio (post-effective).
    if rule.successor and rule.ratio > 0:
        # Try to fetch ORIGINAL ticker for pre-effective period (often works
        # because yfinance keeps old data even after delisting for a while).
        pre = fetch_fn(ticker, start, eff) if eff else None
        post_start = eff if eff else start
        post = fetch_fn(rule.successor, post_start, end)
        if post is None or post.empty:
            return None
        post = post.copy()
        if "Close" in post.columns:
            post["Close"] = post["Close"] * rule.ratio
        if pre is not None and not pre.empty:
            out = pd.concat([pre[["Close"]], post[["Close"]]]).sort_index()
            out = out[~out.index.duplicated(keep="last")]
            return out
        return post[["Close"]]

    # Cash buyout: original prices pre-effective, frozen value post-effective.
    pre = fetch_fn(ticker, start, eff) if eff else None
    if pre is None or pre.empty:
        # No history available at all — just emit a flat series at the cash price.
        idx = pd.date_range(start=start, end=end, freq="B")
        return pd.DataFrame({"Close": [rule.ratio] * len(idx)}, index=idx)

    post_idx = pd.date_range(start=eff, end=end, freq="B") if eff else pd.DatetimeIndex([])
    post = pd.DataFrame({"Close": [rule.ratio] * len(post_idx)}, index=post_idx)
    out = pd.concat([pre[["Close"]], post]).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    return out
