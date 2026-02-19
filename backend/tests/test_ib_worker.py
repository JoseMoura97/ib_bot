import sys
import types


class _FakeIB:
    def __init__(self):
        self._connected = False
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.sleep_calls = 0

    def isConnected(self):
        return self._connected

    def connect(self, host, port, clientId=None, readonly=None, timeout=None):
        self.connect_calls += 1
        self._connected = True
        return True

    def disconnect(self):
        self.disconnect_calls += 1
        self._connected = False

    def sleep(self, _seconds):
        # no-op; just record that we are pumping the loop
        self.sleep_calls += 1

    def managedAccounts(self):
        return ["DU1234567"]

    def accountSummary(self, account_id):
        class _Row:
            def __init__(self, account, tag, value, currency):
                self.account = account
                self.tag = tag
                self.value = value
                self.currency = currency
                self.modelCode = None

        return [
            _Row(account_id, "NetLiquidation", "1000", "USD"),
            _Row(account_id, "AvailableFunds", "500", "USD"),
            _Row(account_id, "TotalCashValue", "200", "USD"),
        ]

    def positions(self, account_id):
        return []


def test_ib_worker_calls_and_stays_connected(monkeypatch):
    # Provide a fake ib_insync module so tests don't require IB Gateway.
    fake_mod = types.ModuleType("ib_insync")
    fake_mod.IB = _FakeIB
    monkeypatch.setitem(sys.modules, "ib_insync", fake_mod)

    from app.services import ib_worker

    # Ensure we start from a clean worker for this test
    ib_worker.stop_ib_worker()

    accounts = ib_worker.call_ib(lambda ib: ib.managedAccounts())
    assert accounts == ["DU1234567"]

    # Multiple calls should reuse the same connection (no explicit disconnects)
    s1 = ib_worker.call_ib(lambda ib: ib.accountSummary("DU1234567"))
    s2 = ib_worker.call_ib(lambda ib: ib.accountSummary("DU1234567"))
    assert len(s1) == len(s2) == 3

    # Stop should disconnect once.
    ib_worker.stop_ib_worker()
