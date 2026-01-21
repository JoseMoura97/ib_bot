from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field


class StrategyOut(BaseModel):
    name: str
    enabled: bool
    config: dict[str, Any] = Field(default_factory=dict)


class StrategyPatch(BaseModel):
    enabled: bool | None = None
    config: dict[str, Any] | None = None


class PortfolioStrategyIn(BaseModel):
    strategy_name: str
    enabled: bool = True
    weight: float = Field(ge=0.0, le=1.0)
    overrides: dict[str, Any] = Field(default_factory=dict)


class PortfolioCreate(BaseModel):
    name: str
    description: str | None = None
    default_cash: float = 100000.0
    settings: dict[str, Any] = Field(default_factory=dict)


class PortfolioOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    default_cash: float
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class PortfolioWithStrategies(PortfolioOut):
    strategies: list[PortfolioStrategyIn] = Field(default_factory=list)


class PortfolioPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    default_cash: float | None = None
    settings: dict[str, Any] | None = None


class RunOut(BaseModel):
    id: UUID
    type: str
    status: str
    params: dict[str, Any] = Field(default_factory=dict)
    progress: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


class CreatePortfolioBacktestRun(BaseModel):
    portfolio_id: UUID
    start_date: str
    end_date: str
    mode: Literal["holdings_union", "nav_blend"]
    rebalance_policy: Literal["per_strategy"] = "per_strategy"
    transaction_cost_bps: float = 0.0


class CreateValidationRun(BaseModel):
    strategies: list[str]
    start_date: str
    end_date: str
    lookback_days_override: int | None = None
    transaction_cost_bps: float = 0.0


class PaperCashSetIn(BaseModel):
    balance: float
    currency: str = "USD"


class PaperCashDeltaIn(BaseModel):
    amount: float


class PaperTradeIn(BaseModel):
    ticker: str
    action: Literal["BUY", "SELL"]
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    strategy: str | None = None
    notes: str | None = None


class PaperRebalanceIn(BaseModel):
    trades: list[PaperTradeIn] = Field(default_factory=list)


# ----------------------------
# Paper trading
# ----------------------------


class PaperAccountCreate(BaseModel):
    name: str | None = None
    currency: str = "USD"
    initial_cash: float = 100000.0


class PaperAccountOut(BaseModel):
    id: int
    name: str
    balance: float
    currency: str
    created_at: datetime
    updated_at: datetime


class PaperFundIn(BaseModel):
    amount: float = Field(gt=0.0)


class PaperPositionOut(BaseModel):
    ticker: str
    quantity: float
    avg_cost: float
    currency: str
    strategy: str | None = None
    updated_at: datetime


class PaperTradeOut(BaseModel):
    timestamp: datetime
    ticker: str
    action: Literal["BUY", "SELL"]
    quantity: float
    price: float
    value: float
    strategy: str | None = None
    notes: str | None = None
    order_id: UUID | None = None


class PaperOrderIn(BaseModel):
    ticker: str = Field(validation_alias=AliasChoices("ticker", "symbol"))
    side: Literal["BUY", "SELL"]
    quantity: float = Field(gt=0.0)
    price: float | None = Field(default=None, gt=0.0, description="Optional override; if omitted, last close is used")
    notes: str | None = None
    strategy: str | None = None


class PaperOrderOut(BaseModel):
    id: UUID
    account_id: int
    created_at: datetime
    ticker: str
    action: Literal["BUY", "SELL"]
    quantity: float
    status: str
    fill_price: float
    value: float


class PaperOrderWithTradeOut(BaseModel):
    order: PaperOrderOut
    trade: PaperTradeOut
    account: PaperAccountOut
    position: PaperPositionOut


class PaperRebalanceRequest(BaseModel):
    portfolio_id: UUID
    allocation_amount: float = Field(
        gt=0.0,
        validation_alias=AliasChoices("allocation_amount", "allocation_usd"),
        description="Dollar amount to allocate for the rebalance",
    )
    account_id: int = Field(default=1, description="Paper account id (default 1)")


class PaperRebalanceLeg(BaseModel):
    ticker: str
    target_weight: float
    price: float
    target_value: float
    target_quantity: float
    current_quantity: float
    delta_quantity: float
    side: Literal["BUY", "SELL"]


class PaperRebalancePreviewOut(BaseModel):
    as_of: datetime
    portfolio_id: UUID
    account_id: int
    allocation_amount: float
    estimated_cash_remaining: float
    legs: list[PaperRebalanceLeg]


class PaperRebalanceExecuteOut(BaseModel):
    as_of: datetime
    portfolio_id: UUID
    account_id: int
    orders: list[PaperOrderOut]
    trades: list[PaperTradeOut]
    account: PaperAccountOut


# ----------------------------
# Allocations ledger
# ----------------------------


class AllocationCreate(BaseModel):
    account_id: str
    portfolio_id: UUID
    amount: float = Field(gt=0.0)
    mode: Literal["paper", "live"] = "paper"
    notes: str | None = None


class AllocationOut(BaseModel):
    id: UUID
    created_at: datetime
    mode: str
    account_id: str
    portfolio_id: UUID
    amount: float
    notes: str | None = None
