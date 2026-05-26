from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(default="sqlite:///./dev.db", validation_alias="DATABASE_URL")
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")

    quiver_api_key: str | None = Field(default=None, validation_alias="QUIVER_API_KEY")

    ib_host: str = Field(default="127.0.0.1", validation_alias="IB_HOST")
    ib_port: int = Field(default=4001, validation_alias="IB_PORT")
    # Optional comma-separated list of account ids to always show in the UI,
    # even if IB doesn't return them via managedAccounts().
    ib_extra_accounts: str | None = Field(default=None, validation_alias="IB_EXTRA_ACCOUNTS")

    price_source: str = Field(default="auto", validation_alias="PRICE_SOURCE")

    enable_live_trading: bool = Field(default=False, validation_alias="ENABLE_LIVE_TRADING")
    market_calendar: str = Field(default="XNYS", validation_alias="MARKET_CALENDAR")
    trading_halt: bool = Field(default=False, validation_alias="TRADING_HALT")
    live_max_exec_per_hour: int = Field(default=20, validation_alias="LIVE_MAX_EXEC_PER_HOUR")
    live_max_orders_per_hour: int = Field(default=200, validation_alias="LIVE_MAX_ORDERS_PER_HOUR")
    live_max_consecutive_errors: int = Field(default=3, validation_alias="LIVE_MAX_CONSECUTIVE_ERRORS")
    live_max_price_age_seconds: int = Field(default=900, validation_alias="LIVE_MAX_PRICE_AGE_SECONDS")
    live_max_price_deviation: float = Field(default=0.2, validation_alias="LIVE_MAX_PRICE_DEVIATION")
    live_max_spread_pct: float = Field(default=0.05, validation_alias="LIVE_MAX_SPREAD_PCT")
    live_max_abs_price: float = Field(default=100000.0, validation_alias="LIVE_MAX_ABS_PRICE")
    live_max_daily_loss_pct: float = Field(default=0.02, validation_alias="LIVE_MAX_DAILY_LOSS_PCT")

    shadow_preview_accounts: str | None = Field(default=None, validation_alias="SHADOW_PREVIEW_ACCOUNTS")
    shadow_preview_portfolios: str | None = Field(default=None, validation_alias="SHADOW_PREVIEW_PORTFOLIOS")
    shadow_preview_allocation: float = Field(default=10000.0, validation_alias="SHADOW_PREVIEW_ALLOCATION")

    live_dry_run: bool = Field(default=False, validation_alias="LIVE_DRY_RUN")
    # Master switch for unattended LIVE auto-rebalancing on each allocation's chosen
    # cadence. Default OFF: even with live trading armed, scheduled live rebalances do
    # nothing until this is explicitly set true. Still subject to all live gates.
    live_auto_rebalance: bool = Field(default=False, validation_alias="LIVE_AUTO_REBALANCE")
    # Fractional shares: when enabled, order quantities keep fractional precision instead
    # of being floored to whole shares (lets small accounts deploy fully and track weights).
    # Requires the IB account to have fractional-shares trading permission. RTH-only fills.
    live_fractional_shares: bool = Field(default=False, validation_alias="LIVE_FRACTIONAL_SHARES")
    live_fractional_decimals: int = Field(default=4, validation_alias="LIVE_FRACTIONAL_DECIMALS")
    live_min_leg_usd: float = Field(default=1.0, validation_alias="LIVE_MIN_LEG_USD")
    live_max_order_pct_nlv: float = Field(default=0.50, validation_alias="LIVE_MAX_ORDER_PCT_NLV")
    live_per_leg_timeout_seconds: int = Field(default=60, validation_alias="LIVE_PER_LEG_TIMEOUT_SECONDS")
    live_allowed_accounts: str | None = Field(default=None, validation_alias="LIVE_ALLOWED_ACCOUNTS")

    telegram_bot_token: str | None = Field(default=None, validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str | None = Field(default=None, validation_alias="TELEGRAM_CHAT_ID")

    api_key: str | None = Field(default=None, validation_alias="API_KEY")
    cors_origins: str = Field(default="", validation_alias="CORS_ORIGINS")

    # ibeam session manager — manages per-user IB gateway containers
    # On Linux Docker the host is the bridge gateway (172.17.0.1); override via env var if needed.
    ibeam_session_manager_url: str = Field(
        default="http://172.17.0.1:5056",
        validation_alias="IBEAM_SESSION_MANAGER_URL",
    )


settings = Settings()  # singleton
