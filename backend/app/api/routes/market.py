from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/treasury-yield")
async def get_treasury_yield():
    """Fetch the current 10-year US Treasury yield from Yahoo Finance (^TNX)."""
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        result = data["chart"]["result"][0]
        meta = result["meta"]
        price = meta.get("regularMarketPrice") or meta.get("previousClose") or 0.0
        # ^TNX is quoted in percentage points (e.g. 4.35 means 4.35%)
        return {
            "rate": round(price / 100, 6),   # decimal form: 0.0435
            "rate_pct": round(price, 4),      # percent form: 4.35
            "symbol": "^TNX",
            "name": "10Y US Treasury",
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch treasury yield: {exc}") from exc
