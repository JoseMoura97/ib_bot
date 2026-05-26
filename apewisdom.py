"""
ApeWisdom WSB mentions client (live-only).

Source: https://apewisdom.io/api/v1.0/filter/{subreddit}/page/{N}
Returns ranked tickers with mention counts + 24h delta.

LIMITATION: ApeWisdom does not expose historical mention data, so this strategy
runs live-only. There is no 3yr backtest equivalent until we either (a) self-build
mention counts from the Reddit pushshift archive or (b) pay for a vendor with
WSB history (Quiver, which gates this dataset on the upgrade tier).

For the IB bot, the practical flow is:
  - Schedule a daily ApeWisdom pull (cron / celery beat)
  - Compute mention-growth signal
  - Paper-trade forward for 4–8 weeks before sizing up
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Optional

import pandas as pd
import requests

log = logging.getLogger(__name__)

_BASE = "https://apewisdom.io/api/v1.0/filter/{subreddit}/page/{page}"
_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache", "apewisdom")
_DEFAULT_UA = "ib_bot/1.0 josemiguelmoura97@gmail.com"


class ApeWisdom:
    """Daily ApeWisdom WSB ticker-mentions snapshot with on-disk cache.

    The API is unauthenticated and lightly rate-limited; we cache one snapshot
    per UTC day so reruns don't hammer the endpoint.
    """

    SUBREDDITS = (
        "wallstreetbets",  # the canonical one
        "stocks",          # more sober retail-investor crowd
        "options",
        "investing",
        "all",             # ApeWisdom's union of the above + others
    )

    def __init__(self, user_agent: Optional[str] = None):
        os.makedirs(_CACHE_DIR, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent or _DEFAULT_UA})
        self._last_request_time = 0.0
        self._min_request_delay = 0.5  # be polite — public API

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_delay:
            time.sleep(self._min_request_delay - elapsed)
        self._last_request_time = time.time()

    def _cache_path(self, subreddit: str, dt: datetime) -> str:
        return os.path.join(
            _CACHE_DIR, f"{subreddit}_{dt.strftime('%Y%m%d')}.csv"
        )

    def get_snapshot(
        self,
        subreddit: str = "wallstreetbets",
        max_pages: int = 5,
        as_of_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Return current mention rankings for `subreddit` across `max_pages` pages.

        Cached per UTC day. Schema:
            rank, ticker, name, mentions, upvotes, rank_24h_ago, mentions_24h_ago,
            growth_24h (mentions / max(mentions_24h_ago, 1))
        """
        subreddit = subreddit.strip().lower()
        if subreddit not in self.SUBREDDITS:
            log.warning(f"ApeWisdom: unknown subreddit '{subreddit}'")
        as_of_date = as_of_date or datetime.utcnow()
        path = self._cache_path(subreddit, as_of_date)

        if os.path.exists(path) and os.path.getsize(path) > 0:
            try:
                return pd.read_csv(path)
            except Exception:
                pass  # fall through and refetch

        rows: list[dict] = []
        for page in range(1, max_pages + 1):
            self._rate_limit()
            url = _BASE.format(subreddit=subreddit, page=page)
            try:
                r = self.session.get(url, timeout=15)
            except Exception as e:
                log.warning(f"ApeWisdom fetch error page={page}: {e}")
                break
            if r.status_code != 200:
                log.warning(f"ApeWisdom status {r.status_code} page={page}")
                break
            try:
                data = r.json()
            except Exception as e:
                log.warning(f"ApeWisdom json parse error page={page}: {e}")
                break
            for row in data.get("results", []):
                rows.append(row)
            # Stop when we've reached the last page
            if page >= int(data.get("pages") or page):
                break

        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        # Coerce numerics
        for c in ("rank", "mentions", "upvotes", "rank_24h_ago", "mentions_24h_ago"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        # Growth signal: today's mentions vs 24h-ago mentions.
        # Cap denominator at 1 to avoid divide-by-zero for newly-trending names.
        if "mentions" in df.columns and "mentions_24h_ago" in df.columns:
            denom = df["mentions_24h_ago"].fillna(0).clip(lower=1)
            df["growth_24h"] = df["mentions"] / denom
        # Persist
        try:
            df.to_csv(path, index=False)
        except Exception as e:
            log.warning(f"ApeWisdom cache write failed: {e}")
        return df

    def top_by_growth(
        self,
        n: int = 10,
        subreddit: str = "wallstreetbets",
        min_mentions: int = 20,
        as_of_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Top-N tickers by 24h mention-growth, filtered to non-trivial absolute mentions.

        `min_mentions` keeps us from picking up noise tickers with 1→3 mention jumps.
        """
        df = self.get_snapshot(
            subreddit=subreddit, as_of_date=as_of_date, max_pages=5
        )
        if df.empty or "growth_24h" not in df.columns:
            return pd.DataFrame()
        f = df[df["mentions"].fillna(0) >= min_mentions].copy()
        # Equal-weight long basket — rename columns for the engine.
        f = f.rename(columns={"ticker": "Ticker"})
        f = f.sort_values("growth_24h", ascending=False).head(n)
        return f.reset_index(drop=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    c = ApeWisdom()
    df = c.top_by_growth(n=10)
    print(f"top-10 by 24h growth (min 20 mentions):")
    if df.empty:
        print("  (no data)")
    else:
        for _, r in df.iterrows():
            print(
                f"  {r['Ticker']:<6} mentions={int(r['mentions']):<5} "
                f"24h_ago={int(r['mentions_24h_ago']):<5} growth={r['growth_24h']:.1f}x"
            )
