"""
Sync Quiver Strategies metadata (About + Key Metrics) from quiverquant.com.

This script fetches:
- https://www.quiverquant.com/strategies/ (strategy list)
- each strategy page under /strategies/s/<name>/

and writes a local JSON cache that QuiverSignals can read as a "database" of
latest strategy descriptions and metrics.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.quiverquant.com"
LIST_URL = f"{BASE_URL}/strategies/"

DEFAULT_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), ".cache", "quiver_strategies_site.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


METRIC_LABELS: Dict[str, str] = {
    "Backtest Start Date": "start_date",
    "Return (1d)": "return_1d",
    "Return (30d)": "return_30d",
    "Return (1Y)": "return_1y",
    "CAGR (Total)": "cagr",
    "Max Drawdown": "max_drawdown",
    "Beta": "beta",
    "Alpha": "alpha",
    "Sharpe Ratio": "sharpe",
    "Win Rate": "win_rate",
    "Average Win": "avg_win",
    "Average Loss": "avg_loss",
    "Annual Volatility": "volatility",
    "Annual Std Dev": "std_dev",
    "Information Ratio": "info_ratio",
    "Treynor Ratio": "treynor",
    "Total Trades": "trades",
}


NUMERIC_KEYS = {"beta", "alpha", "sharpe", "info_ratio", "treynor", "std_dev", "trades"}


@dataclass(frozen=True)
class StrategyPage:
    name: str
    url: str
    description: str
    metrics: Dict[str, Any]


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _fetch(session: requests.Session, url: str, timeout_s: int = 30, retries: int = 3) -> str:
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            resp = session.get(url, headers=HEADERS, timeout=timeout_s)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            last_err = e
            time.sleep(1.0 + attempt * 1.5)
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def _html_to_lines(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    # Normalize whitespace and drop empties
    lines = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        # Collapse internal whitespace
        s = re.sub(r"\s+", " ", s)
        lines.append(s)
    return lines


def _extract_about(lines: List[str]) -> str:
    """
    Extract the About paragraph(s).

    Strategy pages repeat the About section; we take the first one.
    """
    try:
        idx = lines.index("About")
    except ValueError:
        return ""

    out: List[str] = []
    for s in lines[idx + 1 :]:
        # Stop when metrics start
        if s in {"Backtest Start Date", "Key Metrics", "Portfolio Insight", "Holdings"}:
            break
        # Avoid re-capturing the second About header
        if s == "About":
            break
        out.append(s)
    about = " ".join(out).strip()
    about = re.sub(r"\s+", " ", about)
    return about


def _parse_numeric(value: str, key: str) -> Any:
    if key == "trades":
        m = re.search(r"(-?\d+)", value.replace(",", ""))
        return int(m.group(1)) if m else value
    # floats
    try:
        return float(value.replace(",", ""))
    except Exception:
        return value


def _extract_metrics(lines: List[str]) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    # Build an index for quick lookup (first occurrence wins)
    pos: Dict[str, int] = {}
    for i, s in enumerate(lines):
        if s in METRIC_LABELS and s not in pos:
            pos[s] = i

    for label, key in METRIC_LABELS.items():
        i = pos.get(label)
        if i is None:
            continue
        # Value is usually next non-empty line
        val = None
        for j in range(i + 1, min(i + 6, len(lines))):
            if lines[j] and lines[j] not in METRIC_LABELS:
                val = lines[j]
                break
        if val is None:
            continue

        # Normalize
        if key in NUMERIC_KEYS:
            metrics[key] = _parse_numeric(val, key)
        else:
            metrics[key] = val
    return metrics


def _parse_strategy_page(html: str, url: str) -> StrategyPage:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    name = h1.get_text(strip=True) if h1 else ""
    # Strategy pages usually title as "<Name> Strategy"
    if name.endswith(" Strategy"):
        name = name[: -len(" Strategy")].strip()
    lines = _html_to_lines(html)
    about = _extract_about(lines)
    metrics = _extract_metrics(lines)

    # Prefer "CAGR (Total)" to map to cagr string
    return StrategyPage(
        name=name or metrics.get("strategy", "") or url,
        url=url,
        description=about,
        metrics=metrics,
    )


def fetch_strategy_urls(session: requests.Session) -> List[str]:
    html = _fetch(session, LIST_URL)
    soup = BeautifulSoup(html, "html.parser")
    urls = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if not href:
            continue
        if href.startswith("/strategies/s/"):
            urls.add(urljoin(BASE_URL, href))
    return sorted(urls)


def sync_all(output_path: str = DEFAULT_OUTPUT_PATH, sleep_s: float = 0.15) -> Dict[str, Any]:
    _ensure_parent_dir(output_path)
    session = requests.Session()
    strategy_urls = fetch_strategy_urls(session)

    strategies: Dict[str, Dict[str, Any]] = {}
    errors: List[Dict[str, str]] = []

    for i, url in enumerate(strategy_urls):
        try:
            html = _fetch(session, url)
            page = _parse_strategy_page(html, url)
            name = page.name.strip()
            if not name:
                raise RuntimeError("Missing strategy name")

            row: Dict[str, Any] = dict(page.metrics)
            if page.description:
                row["description"] = page.description
            row["source_url"] = page.url

            # Ensure start_date is ISO (if present)
            if "start_date" in row and isinstance(row["start_date"], str):
                row["start_date"] = row["start_date"].strip()

            strategies[name] = row
        except Exception as e:
            errors.append({"url": url, "error": str(e)})

        # be polite
        if sleep_s:
            time.sleep(sleep_s)

    payload = {
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "source": LIST_URL,
        "n_strategies": len(strategies),
        "n_errors": len(errors),
        "errors": errors[:50],
        "strategies": strategies,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return payload


if __name__ == "__main__":
    out = os.getenv("QUIVER_STRATEGY_CACHE_PATH", DEFAULT_OUTPUT_PATH)
    payload = sync_all(output_path=out)
    print(f"Wrote {payload['n_strategies']} strategies to {out} (errors={payload['n_errors']})")
