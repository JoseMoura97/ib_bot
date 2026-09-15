"""
Phase p2 — IB API response parsing hardening.

Every parser between the raw ib_insync/ibapi response and downstream
execution (account discovery, positions, account values/NLV, ticker/price
quotes, order/execution results) must reject or safely no-op on malformed
payloads -- missing keys, wrong types, null/empty values, and unexpected
extra fields -- WITHOUT ever reaching a broker order placement call. Valid
fixtures must still parse to the exact expected result.

Each parser is exercised with five fixture categories: missing-key,
wrong-type, null/empty, extra-field, and valid.
"""
from __future__ import annotations

import sys
import types
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.config import settings


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


class _NoAttrs:
    """An object with NO attributes at all -- the extreme missing-key case.
    getattr(obj, "anything", default) must fall through to `default`."""

    __slots__ = ()


def _av(**kw) -> SimpleNamespace:
    """Build an AccountValue-like fixture."""
    return SimpleNamespace(**kw)


def _pos(**kw) -> SimpleNamespace:
    """Build a Position-like fixture."""
    return SimpleNamespace(**kw)


def _contract(**kw) -> SimpleNamespace:
    return SimpleNamespace(**kw)


# ===========================================================================
# 1. app.api.routes.ib._normalize_accounts -- managedAccounts() payload shapes
# ===========================================================================


class TestNormalizeAccounts:
    def test_missing_key_returns_empty(self):
        # "missing key" for a top-level scalar payload == the field is absent (None).
        from app.api.routes.ib import _normalize_accounts

        assert _normalize_accounts(None) == []

    def test_wrong_type_int_is_stringified_not_raised(self):
        from app.api.routes.ib import _normalize_accounts

        # Some wrapper misbehaves and returns a bare int instead of list/str.
        assert _normalize_accounts(12345) == ["12345"]

    def test_wrong_type_nested_non_string_items(self):
        from app.api.routes.ib import _normalize_accounts

        assert _normalize_accounts([1, 2, None]) == ["1", "2"]

    def test_null_and_empty_variants(self):
        from app.api.routes.ib import _normalize_accounts

        assert _normalize_accounts("") == []
        assert _normalize_accounts([]) == []
        assert _normalize_accounts([""]) == []
        assert _normalize_accounts(["", None, "  "]) == []

    def test_extra_separators_are_ignored_extra_data(self):
        from app.api.routes.ib import _normalize_accounts

        # Comma-separated string inside a list element (ibapi quirk) plus
        # stray whitespace/semicolon separators -- must still dedupe cleanly.
        assert _normalize_accounts(["U1,U2;U3\nU4  U1"]) == ["U1", "U2", "U3", "U4"]

    def test_valid_list(self):
        from app.api.routes.ib import _normalize_accounts

        assert _normalize_accounts(["U1", "U2", "U3"]) == ["U1", "U2", "U3"]

    def test_valid_comma_string(self):
        from app.api.routes.ib import _normalize_accounts

        assert _normalize_accounts("U1,U2,U3") == ["U1", "U2", "U3"]


# ===========================================================================
# 2. app.api.routes.ib._managed_accounts -- multi-source account discovery
# ===========================================================================


class TestManagedAccounts:
    def test_missing_key_all_sources_absent_no_crash(self):
        from app.api.routes.ib import _managed_accounts

        class FakeIb:
            def managedAccounts(self):
                raise AttributeError("no such attribute on this wrapper version")

            def accountSummary(self, *a, **kw):
                raise AttributeError("not supported")

        assert _managed_accounts(FakeIb()) == []

    def test_wrong_type_primary_source_does_not_win_over_richer_fallback(self):
        from app.api.routes.ib import _managed_accounts

        class FakeIb:
            def managedAccounts(self):
                return 999  # wrong type: bare int instead of list[str]

            wrapper = SimpleNamespace(accounts=None)

            def accountSummary(self, *a, **kw):
                return [_av(account="U9"), _av(account="U10")]

        # a3 (2 accounts) is richer than a1 (["999"], 1 account) -> a3 wins.
        assert _managed_accounts(FakeIb()) == ["U9", "U10"]

    def test_null_empty_everywhere_returns_empty_list(self):
        from app.api.routes.ib import _managed_accounts

        class FakeIb:
            def managedAccounts(self):
                return None

            wrapper = SimpleNamespace(accounts=[])

            def accountSummary(self, *a, **kw):
                return []

        assert _managed_accounts(FakeIb()) == []

    def test_extra_field_on_rows_is_ignored(self):
        from app.api.routes.ib import _managed_accounts

        class FakeIb:
            def managedAccounts(self):
                return ["U1", "U2"]

            wrapper = SimpleNamespace(accounts=["U1", "U2"])

            def accountSummary(self, *a, **kw):
                return [_av(account="U1", tag="NetLiquidation", value="1", currency="USD", unexpectedField=object())]

        assert _managed_accounts(FakeIb()) == ["U1", "U2"]

    def test_valid(self):
        from app.api.routes.ib import _managed_accounts

        class FakeIb:
            def managedAccounts(self):
                return ["U1", "U2", "U3"]

            wrapper = SimpleNamespace(accounts=["U1", "U2", "U3"])

            def accountSummary(self, *a, **kw):
                return []

        assert _managed_accounts(FakeIb()) == ["U1", "U2", "U3"]


# ===========================================================================
# 3. app.api.routes.ib._account_values_for_account / _positions_for_account
# ===========================================================================


class TestAccountValuesForAccount:
    def test_missing_key_no_methods_returns_empty(self):
        from app.api.routes.ib import _account_values_for_account

        assert _account_values_for_account(_NoAttrs(), "U1") == []

    def test_wrong_type_single_dict_instead_of_list_does_not_crash_downstream(self):
        from app.api.routes.ib import _account_values_for_account, _account_values_to_dicts

        class FakeIb:
            def accountValues(self, account_id):
                return {"tag": "NetLiquidation"}  # wrong type: dict, not list[AccountValue]

        rows = _account_values_for_account(FakeIb(), "U1")
        dicts = _account_values_to_dicts(rows)
        # Iterating a dict yields its string keys; getattr(str, "account", None)
        # must safely fall through to None for every field, never raise.
        assert all(d["account"] is None and d["value"] is None for d in dicts)

    def test_null_empty_falls_through_all_sources_to_empty(self):
        from app.api.routes.ib import _account_values_for_account

        class FakeIb:
            def accountValues(self, account_id):
                return None

            def accountSummary(self, *a, **kw):
                return None

        assert _account_values_for_account(FakeIb(), "U1") == []

    def test_extra_field_preserved_but_ignored_by_extraction(self):
        from app.api.routes.ib import _account_values_for_account
        from app.api.routes.live import _extract_nlv

        class FakeIb:
            def accountValues(self, account_id):
                return [_av(account="U1", tag="NetLiquidation", value="123456.78", currency="USD", modelCode=None, futureField="unexpected")]

        rows = _account_values_for_account(FakeIb(), "U1")
        assert _extract_nlv(rows) == pytest.approx(123456.78)

    def test_valid_prefers_account_values(self):
        from app.api.routes.ib import _account_values_for_account

        class FakeIb:
            def accountValues(self, account_id):
                return [_av(account=account_id, tag="NetLiquidation", value="100.0", currency="USD")]

        rows = _account_values_for_account(FakeIb(), "U1")
        assert len(rows) == 1
        assert rows[0].tag == "NetLiquidation"

    def test_valid_falls_back_to_account_summary_group_all_and_filters(self):
        from app.api.routes.ib import _account_values_for_account

        class FakeIb:
            def accountValues(self, account_id):
                return []

            def accountSummary(self, *a, **kw):
                # accountSummary(account_id) (step 2) is unsupported by this
                # wrapper and returns nothing; only accountSummary(group="All")
                # (step 3) returns rows, which the caller must then filter.
                if kw.get("group") == "All" or (a and a[0] == "All"):
                    return [
                        _av(account="U1", tag="NetLiquidation", value="1.0", currency="USD"),
                        _av(account="U2", tag="NetLiquidation", value="2.0", currency="USD"),
                    ]
                return []

        rows = _account_values_for_account(FakeIb(), "U1")
        assert len(rows) == 1
        assert rows[0].account == "U1"


class TestPositionsForAccount:
    def test_missing_key_no_methods_returns_empty(self):
        from app.api.routes.ib import _positions_for_account

        assert _positions_for_account(_NoAttrs(), "U1") == []

    def test_wrong_type_position_field_excluded_downstream(self):
        from app.api.routes.ib import _positions_for_account
        from app.api.routes.live import _to_float

        class FakeIb:
            def positions(self, account_id):
                return [_pos(account=account_id, position="not-a-number", avgCost=10.0, contract=_contract(symbol="BAD"))]

        rows = _positions_for_account(FakeIb(), "U1")
        assert len(rows) == 1
        assert _to_float(rows[0].position) is None

    def test_null_empty_returns_empty(self):
        from app.api.routes.ib import _positions_for_account

        class FakeIb:
            def positions(self, account_id=None):
                return None

        assert _positions_for_account(FakeIb(), "U1") == []

    def test_extra_field_ignored(self):
        from app.api.routes.ib import _positions_for_account, _positions_to_dicts

        class FakeIb:
            def positions(self, account_id):
                return [_pos(account=account_id, position=5.0, avgCost=10.0, contract=_contract(conId=1, symbol="AAPL", secType="STK", currency="USD", exchange="SMART", extraVendorField="whatever"))]

        rows = _positions_for_account(FakeIb(), "U1")
        dicts = _positions_to_dicts(rows)
        assert dicts == [
            {
                "account": "U1",
                "position": 5.0,
                "avgCost": 10.0,
                "contract": {
                    "conId": 1,
                    "symbol": "AAPL",
                    "localSymbol": None,
                    "secType": "STK",
                    "currency": "USD",
                    "exchange": "SMART",
                    "primaryExchange": None,
                },
            }
        ]

    def test_valid_filters_by_account_on_fallback(self):
        from app.api.routes.ib import _positions_for_account

        class FakeIb:
            def positions(self, account_id):
                return []

            def positions_all(self):
                return []

            def positions(self, account_id=None):  # noqa: F811 - overriding intentional per ib_insync signature
                if account_id:
                    return []
                return [
                    _pos(account="U1", position=1.0, avgCost=1.0, contract=_contract(symbol="AAA")),
                    _pos(account="U2", position=2.0, avgCost=2.0, contract=_contract(symbol="BBB")),
                ]

        rows = _positions_for_account(FakeIb(), "U1")
        assert len(rows) == 1
        assert rows[0].account == "U1"


# ===========================================================================
# 4. app.api.routes.live -- numeric tag extraction (NLV / realized / unrealized PnL)
# ===========================================================================


@pytest.mark.parametrize(
    "extractor_name,tag",
    [
        ("_extract_nlv", "NetLiquidation"),
        ("_extract_realized_pnl", "RealizedPnL"),
        ("_extract_unrealized_pnl", "UnrealizedPnL"),
    ],
)
class TestTagExtractors:
    def _extractor(self, extractor_name):
        import app.api.routes.live as live_routes

        return getattr(live_routes, extractor_name)

    def test_missing_key_row_has_no_attrs(self, extractor_name, tag):
        fn = self._extractor(extractor_name)
        assert fn([_NoAttrs()]) is None

    def test_wrong_type_value_is_a_list(self, extractor_name, tag):
        fn = self._extractor(extractor_name)
        row = _av(tag=tag, currency="USD", value=[1, 2, 3])
        assert fn([row]) is None

    def test_null_empty_rows(self, extractor_name, tag):
        fn = self._extractor(extractor_name)
        assert fn([]) is None
        assert fn(None) is None
        assert fn([_av(tag=tag, currency="USD", value=None)]) is None
        assert fn([_av(tag=tag, currency="USD", value="")]) is None

    def test_extra_field_on_row_is_ignored(self, extractor_name, tag):
        fn = self._extractor(extractor_name)
        row = _av(tag=tag, currency="USD", value="42.5", modelCode="", unexpectedVendorField={"nested": True})
        assert fn([row]) == pytest.approx(42.5)

    def test_valid_skips_wrong_tag_and_currency_then_matches(self, extractor_name, tag):
        fn = self._extractor(extractor_name)
        rows = [
            _av(tag="SomeOtherTag", currency="USD", value="999"),
            _av(tag=tag, currency="EUR", value="999"),
            _av(tag=tag, currency="USD", value="42.5"),
        ]
        assert fn(rows) == pytest.approx(42.5)


class TestToFloat:
    """_to_float is duplicated verbatim in both ib.py and live.py; test both."""

    @pytest.mark.parametrize("module_name", ["app.api.routes.ib", "app.api.routes.live"])
    def test_missing_null_wrong_type_and_valid(self, module_name):
        import importlib

        mod = importlib.import_module(module_name)
        to_float = mod._to_float

        assert to_float(None) is None
        assert to_float("") is None
        assert to_float("   ") is None
        assert to_float("not-a-number") is None
        assert to_float([1, 2, 3]) is None
        assert to_float({"a": 1}) is None
        assert to_float(object()) is None
        assert to_float(5) == 5.0
        assert to_float(5.5) == 5.5
        assert to_float("5.5") == 5.5
        assert to_float("  5.5  ") == 5.5


# ===========================================================================
# 5. app.api.routes.live._current_positions_for_account -- via call_ib
# ===========================================================================


class TestCurrentPositionsForAccount:
    def _run(self, monkeypatch, positions_response):
        import app.api.routes.live as live_routes

        class FakeIb:
            def positions(self, account_id=None):
                return positions_response

        monkeypatch.setattr(live_routes, "call_ib", lambda fn, timeout=10.0: fn(FakeIb()))
        return live_routes._current_positions_for_account("U1")

    def test_missing_key_contract_absent_skips_row(self, monkeypatch):
        rows = [_pos(account="U1", position=5.0)]  # no `contract` attribute at all
        assert self._run(monkeypatch, rows) == {}

    def test_wrong_type_position_value_skips_row(self, monkeypatch):
        rows = [_pos(account="U1", position="garbage", contract=_contract(symbol="AAPL"))]
        assert self._run(monkeypatch, rows) == {}

    def test_null_empty_positions_list(self, monkeypatch):
        assert self._run(monkeypatch, []) == {}
        assert self._run(monkeypatch, None) == {}

    def test_extra_field_ignored_valid_row_still_parses(self, monkeypatch):
        rows = [_pos(account="U1", position=12.5, avgCost=1.0, unexpectedField="x", contract=_contract(symbol="AAPL", vendorExtra=True))]
        assert self._run(monkeypatch, rows) == {"AAPL": 12.5}

    def test_valid_uses_local_symbol_fallback(self, monkeypatch):
        rows = [_pos(account="U1", position=3.0, contract=_contract(symbol=None, localSymbol="AAPL.US"))]
        assert self._run(monkeypatch, rows) == {"AAPL.US": 3.0}

    def test_valid_multiple_positions(self, monkeypatch):
        rows = [
            _pos(account="U1", position=3.0, contract=_contract(symbol="AAPL")),
            _pos(account="U1", position=-2.0, contract=_contract(symbol="MSFT")),
        ]
        assert self._run(monkeypatch, rows) == {"AAPL": 3.0, "MSFT": -2.0}


# ===========================================================================
# 6. app.api.routes.live._fetch_live_quotes -- ticker/price parsing
# ===========================================================================


@pytest.fixture()
def _stub_ib_insync(monkeypatch):
    class _Stock:
        def __init__(self, symbol, exchange="SMART", currency="USD"):
            self.symbol = symbol

    class _MarketOrder:
        def __init__(self, action, total_quantity):
            self.action = action
            self.totalQuantity = total_quantity
            self.orderId = 0
            self.permId = 0
            self.account = ""

    stub = types.ModuleType("ib_insync")
    stub.Stock = _Stock
    stub.MarketOrder = _MarketOrder
    monkeypatch.setitem(sys.modules, "ib_insync", stub)
    return stub


class _Ticker:
    """ib_insync.Ticker-like fixture. marketPrice() raises by default (as the
    real object does when there is no live tick yet), forcing the fallback to
    .last / .close, exactly like production."""

    def __init__(self, contract=None, bid=None, ask=None, last=None, close=None, time=None, market_price=None, extra=None):
        if contract is not None:
            self.contract = contract
        self.bid = bid
        self.ask = ask
        self.last = last
        self.close = close
        self.time = time
        self._market_price = market_price
        if extra is not None:
            self.vendorExtraField = extra

    def marketPrice(self):
        if self._market_price is None:
            raise ValueError("no market price available")
        return self._market_price


class TestFetchLiveQuotes:
    def _run(self, monkeypatch, tickers_response, *, tickers=("AAPL",)):
        import app.api.routes.live as live_routes

        class FakeIb:
            def qualifyContracts(self, *contracts):
                pass

            def reqTickers(self, *contracts):
                return tickers_response

        monkeypatch.setattr(live_routes, "call_ib", lambda fn, timeout=20.0: fn(FakeIb()))
        return live_routes._fetch_live_quotes(tickers)

    def test_missing_key_no_contract_attribute_is_skipped(self, monkeypatch, _stub_ib_insync):
        ticks = [_Ticker(contract=None, market_price=100.0)]
        # _Ticker with contract=None never sets self.contract -> getattr defaults to None.
        assert self._run(monkeypatch, ticks) == {}

    def test_wrong_type_price_fields_are_skipped_not_raised(self, monkeypatch, _stub_ib_insync):
        ticks = [_Ticker(contract=_contract(symbol="AAPL"), last="not-a-number", close={"nested": 1})]
        # marketPrice() raises (no market_price given), last/close are wrong-type -> price is None -> excluded.
        assert self._run(monkeypatch, ticks) == {}

    def test_null_empty_ticker_list(self, monkeypatch, _stub_ib_insync):
        assert self._run(monkeypatch, []) == {}
        assert self._run(monkeypatch, None) == {}

    def test_null_price_and_close_skipped(self, monkeypatch, _stub_ib_insync):
        ticks = [_Ticker(contract=_contract(symbol="AAPL"), last=None, close=None)]
        assert self._run(monkeypatch, ticks) == {}

    def test_extra_field_on_ticker_ignored_when_otherwise_valid(self, monkeypatch, _stub_ib_insync):
        import app.api.routes.live as live_routes

        monkeypatch.setattr(
            live_routes,
            "fetch_last_close_price",
            lambda t: live_routes.PriceQuote(ticker=t, price=100.0, as_of=datetime.utcnow(), source="test"),
        )
        ticks = [_Ticker(contract=_contract(symbol="AAPL"), market_price=100.0, bid=99.9, ask=100.1, extra="unexpected-vendor-data")]
        quotes = self._run(monkeypatch, ticks)
        assert set(quotes.keys()) == {"AAPL"}
        assert quotes["AAPL"].price == 100.0

    def test_wrong_type_ticks_not_iterable_raises_and_never_yields_quotes(self, monkeypatch, _stub_ib_insync):
        import app.api.routes.live as live_routes

        # A gateway bug/wrapper mismatch could return a bare non-iterable
        # object instead of a list of Ticker. The parser must fail loudly
        # (never silently fabricate a quote) so nothing downstream executes.
        with pytest.raises(TypeError):
            self._run(monkeypatch, 12345)

    def test_valid_price_zero_or_negative_is_rejected(self, monkeypatch, _stub_ib_insync):
        from fastapi import HTTPException

        ticks = [_Ticker(contract=_contract(symbol="AAPL"), market_price=0.0)]
        with pytest.raises(HTTPException) as exc:
            self._run(monkeypatch, ticks)
        assert exc.value.status_code == 400

    def test_valid_stale_quote_is_rejected(self, monkeypatch, _stub_ib_insync):
        from fastapi import HTTPException

        stale_time = datetime.utcnow() - timedelta(seconds=settings.live_max_price_age_seconds + 60)
        ticks = [_Ticker(contract=_contract(symbol="AAPL"), market_price=100.0, time=stale_time)]
        with pytest.raises(HTTPException) as exc:
            self._run(monkeypatch, ticks)
        assert "stale" in str(exc.value.detail)

    def test_valid_parses_expected_result(self, monkeypatch, _stub_ib_insync):
        import app.api.routes.live as live_routes

        monkeypatch.setattr(
            live_routes,
            "fetch_last_close_price",
            lambda t: live_routes.PriceQuote(ticker=t, price=150.0, as_of=datetime.utcnow(), source="test"),
        )
        ticks = [_Ticker(contract=_contract(symbol="AAPL"), market_price=150.0, bid=149.9, ask=150.1)]
        quotes = self._run(monkeypatch, ticks)
        assert set(quotes.keys()) == {"AAPL"}
        q = quotes["AAPL"]
        assert q.ticker == "AAPL"
        assert q.price == 150.0
        assert q.source == "ib"


# ===========================================================================
# 7. Broker-stub end-to-end: malformed IB responses must reach ZERO orders;
#    a valid fixture must place exactly the expected order.
# ===========================================================================


class FakeBrokerIB:
    """Records every placeOrder() call so tests can assert on broker-stub
    order counts -- the acceptance-level proof that malformed data never
    reaches order execution."""

    def __init__(self, *, tickers_response, positions_response=None, account_values_response=None):
        self.tickers_response = tickers_response
        self.positions_response = positions_response or []
        self.account_values_response = account_values_response or []
        self.placed_orders: list[tuple[str, str, float]] = []
        self.open_orders: list[object] = []

    def qualifyContracts(self, *contracts):
        pass

    def reqTickers(self, *contracts):
        return self.tickers_response

    def positions(self, account_id=None):
        return self.positions_response

    def accountValues(self, account_id=None):
        return self.account_values_response

    def accountSummary(self, *a, **kw):
        return self.account_values_response

    def managedAccounts(self):
        return ["U111111"]

    def reqAllOpenOrders(self):
        return self.open_orders

    def placeOrder(self, contract, order):
        self.placed_orders.append((getattr(contract, "symbol", None), order.action, order.totalQuantity))
        return SimpleNamespace(
            orderStatus=SimpleNamespace(status="Filled", filled=order.totalQuantity, remaining=0.0, avgFillPrice=100.0),
            order=SimpleNamespace(orderId=1, permId=1),
            fills=[],
        )

    def cancelOrder(self, order):
        pass

    def sleep(self, n):
        pass


_ACCOUNT_ID = "U111111"
_PORTFOLIO_ID = "00000000-0000-0000-0000-000000000099"


def _exec_body(**overrides):
    return {
        "account_id": _ACCOUNT_ID,
        "portfolio_id": _PORTFOLIO_ID,
        "allocation_amount": 10_000.0,
        "max_orders": 5,
        "allow_short": False,
        "confirm": True,
        **overrides,
    }


@pytest.fixture(autouse=True)
def _live_env(monkeypatch):
    monkeypatch.setattr(settings, "enable_live_trading", True)
    monkeypatch.setattr(settings, "live_dry_run", False)
    monkeypatch.setattr(settings, "trading_halt", False)


def _wire_common(monkeypatch, fake_ib):
    monkeypatch.setattr("app.api.routes.live._assert_account_allowed", lambda *a: None)
    monkeypatch.setattr("app.api.routes.live.market_is_open", lambda *a: (True, None))
    monkeypatch.setattr("app.api.routes.live._account_total_pnl", lambda *a: (0.0, 0.0))
    monkeypatch.setattr("app.api.routes.live._account_nlv", lambda *a: 200_000.0)
    monkeypatch.setattr("app.api.routes.live._build_target_weights", lambda *a, **kw: {"BADTICK": 1.0})
    monkeypatch.setattr("app.api.routes.live.call_ib", lambda fn, timeout=10.0: fn(fake_ib))
    monkeypatch.setattr("app.services.alerting.send_error_alert", lambda *a, **kw: None)
    monkeypatch.setattr("app.services.alerting.send_rebalance_alert", lambda *a, **kw: None)


class TestBrokerStubZeroOrdersOnMalformed:
    """Each malformed reqTickers() fixture must never let execution reach
    ib.placeOrder(); the request must be rejected before the broker call."""

    @pytest.mark.parametrize(
        "label,tickers_response",
        [
            ("missing_key_no_contract", [SimpleNamespace(last=100.0)]),
            ("wrong_type_price_fields", [SimpleNamespace(contract=SimpleNamespace(symbol="BADTICK"), last="garbage", close=[1, 2])]),
            ("null_empty_ticker_list", []),
            ("null_price_fields", [SimpleNamespace(contract=SimpleNamespace(symbol="BADTICK"), last=None, close=None)]),
        ],
    )
    def test_malformed_fixture_yields_zero_broker_orders(self, client, db_session, monkeypatch, label, tickers_response, _stub_ib_insync):
        fake_ib = FakeBrokerIB(tickers_response=tickers_response)
        _wire_common(monkeypatch, fake_ib)

        resp = client.post(
            "/live/rebalance/execute",
            json=_exec_body(),
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )

        assert resp.status_code >= 400, f"[{label}] malformed IB response must be rejected, got {resp.status_code}: {resp.text}"
        assert "ib_insync import failed" not in resp.text, f"[{label}] rejection must come from response validation, not a missing dependency: {resp.text}"
        assert fake_ib.placed_orders == [], f"[{label}] malformed IB response must never reach placeOrder(); got {fake_ib.placed_orders}"


class TestBrokerStubValidFixtureExecutes:
    def test_valid_fixture_places_exactly_expected_order(self, client, db_session, monkeypatch, _stub_ib_insync):
        import app.api.routes.live as live_routes

        monkeypatch.setattr(
            live_routes,
            "fetch_last_close_price",
            lambda t: live_routes.PriceQuote(ticker=t, price=100.0, as_of=datetime.utcnow(), source="test"),
        )

        valid_ticker = SimpleNamespace(
            contract=SimpleNamespace(symbol="BADTICK"),
            bid=99.9,
            ask=100.1,
            last=100.0,
            close=100.0,
            time=datetime.utcnow(),
        )
        # marketPrice() must exist per the real ib_insync.Ticker API.
        valid_ticker.marketPrice = lambda: 100.0

        fake_ib = FakeBrokerIB(tickers_response=[valid_ticker], positions_response=[])
        _wire_common(monkeypatch, fake_ib)

        resp = client.post(
            "/live/rebalance/execute",
            json=_exec_body(),
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )

        assert resp.status_code == 200, resp.text
        assert len(fake_ib.placed_orders) == 1
        symbol, action, qty = fake_ib.placed_orders[0]
        assert symbol == "BADTICK"
        assert action == "BUY"
        assert qty == pytest.approx(100.0)  # $10,000 allocation / $100 price
