from __future__ import annotations

from datetime import datetime

from app.models.portfolio import Portfolio, PortfolioStrategy
from app.models.strategy import Strategy
from app.services.paper_trading import PriceQuote


def _seed_portfolio(db_session) -> str:
    strategy = Strategy(name="Test Strategy", enabled=True, config={})
    portfolio = Portfolio(name="Test Portfolio", description="paper cycle test", default_cash=100000.0, settings={})
    db_session.add(strategy)
    db_session.add(portfolio)
    db_session.flush()

    link = PortfolioStrategy(
        portfolio_id=portfolio.id,
        strategy_name=strategy.name,
        enabled=True,
        weight=1.0,
        overrides={},
    )
    db_session.add(link)
    db_session.commit()
    return str(portfolio.id)


def test_paper_rebalance_cycles(client, db_session, monkeypatch):
    portfolio_id = _seed_portfolio(db_session)

    def _fake_fetch_prices(tickers):
        now = datetime.utcnow()
        return {str(t).upper(): PriceQuote(ticker=str(t).upper(), price=100.0, as_of=now, source="test") for t in tickers}

    monkeypatch.setattr("app.api.routes.paper.fetch_prices", _fake_fetch_prices)

    account_id = 1
    for i in range(10):
        allocation_amount = 10000.0 if i % 2 == 0 else 11000.0
        payload = {
            "portfolio_id": portfolio_id,
            "allocation_amount": allocation_amount,
            "account_id": account_id,
        }

        preview = client.post("/paper/rebalance/preview", json=payload)
        assert preview.status_code == 200
        preview_data = preview.json()
        legs = preview_data.get("legs", [])
        assert len(legs) > 0

        execute = client.post("/paper/rebalance/execute", json=payload)
        assert execute.status_code == 200
        execute_data = execute.json()

        orders = execute_data.get("orders", [])
        trades = execute_data.get("trades", [])
        assert len(orders) == len(trades) == len(legs)

        summary = client.get(f"/paper/accounts/{account_id}/summary")
        assert summary.status_code == 200
        summary_data = summary.json()
        assert summary_data["cash"] >= 0
        assert summary_data["equity"] >= summary_data["cash"]
