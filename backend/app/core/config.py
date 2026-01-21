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

    price_source: str = Field(default="auto", validation_alias="PRICE_SOURCE")

    enable_live_trading: bool = Field(default=False, validation_alias="ENABLE_LIVE_TRADING")


settings = Settings()  # singleton
