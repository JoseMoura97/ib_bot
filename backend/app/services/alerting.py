"""
Telegram alerting service.

Sends fire-and-forget alerts via the Telegram Bot API.
Degrades gracefully to log-only when TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID are not configured.
"""
from __future__ import annotations

import logging
from typing import Literal

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

AlertLevel = Literal["info", "warning", "error", "critical"]

_LEVEL_EMOJI = {
    "info": "\u2139\ufe0f",
    "warning": "\u26a0\ufe0f",
    "error": "\u274c",
    "critical": "\U0001f6a8",
}


def _telegram_configured() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def send_alert(level: AlertLevel, message: str) -> bool:
    """
    Send an alert. Returns True if delivered to Telegram, False otherwise.
    Never raises -- failures are logged and swallowed.
    """
    prefix = _LEVEL_EMOJI.get(level, "")
    full_message = f"{prefix} [{level.upper()}] {message}"

    logger.log(
        {"info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR, "critical": logging.CRITICAL}.get(level, logging.INFO),
        "ALERT: %s",
        full_message,
    )

    if not _telegram_configured():
        return False

    try:
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": settings.telegram_chat_id,
            "text": full_message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code != 200:
                logger.warning("Telegram API returned %s: %s", resp.status_code, resp.text[:200])
                return False
        return True
    except Exception as e:
        logger.warning("Failed to send Telegram alert: %s", e)
        return False


def send_trade_alert(action: str, details: str) -> bool:
    return send_alert("info", f"<b>Trade:</b> {action}\n{details}")


def send_rebalance_alert(status: str, details: str) -> bool:
    level: AlertLevel = "info" if status == "OK" else "error"
    return send_alert(level, f"<b>Rebalance {status}:</b>\n{details}")


def send_halt_alert(triggered_by: str = "manual") -> bool:
    return send_alert("critical", f"<b>TRADING HALTED</b> (triggered by: {triggered_by})")


def send_resume_alert(triggered_by: str = "manual") -> bool:
    return send_alert("warning", f"<b>Trading resumed</b> (triggered by: {triggered_by})")


def send_daily_pnl_alert(account_id: str, equity: float, daily_pnl: float) -> bool:
    sign = "+" if daily_pnl >= 0 else ""
    return send_alert(
        "info",
        f"<b>Daily P&L:</b> account={account_id}\n"
        f"Equity: ${equity:,.2f} | Day: {sign}${daily_pnl:,.2f}",
    )


def send_error_alert(context: str, error: str) -> bool:
    return send_alert("error", f"<b>{context}:</b>\n{error}")
