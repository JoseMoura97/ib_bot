# IB Gateway top-3, p3 — web-client order guard receipt

**Implementation commit:** `6e93a90366bd2268d63a61aaf315339ce50f9ebf`

## Scope audit

`system/execution/ib_web_client.py` has one Client Portal order endpoint call:
`iserver_place_orders`.  It is contained exclusively in
`IBWebClient._submit_guarded_order()`.  `place_market_order()` validates its
input and routes the generated order through that wrapper; there is no second
web-client placement wrapper.

The wrapper holds one lock while it reads the socket-free shared Gateway
snapshot, applies the shared account/halt/per-order/aggregate-notional policy,
checks and reserves the idempotency key, and invokes Client Portal.  A failed
Client Portal response retains the key because a retry could duplicate an order
whose broker outcome is unknown.

## Executed verification

```bash
/home/servidor/Desktop/cursor-projects/ib_bot/.venv/bin/python -m pytest -q \
  backend/tests/test_ib_web_client_order_guard.py \
  backend/tests/test_live_order_guard_bypass.py \
  backend/tests/test_ib_gateway_state_guard.py
```

Result: **30 passed**, 0 failed (warnings only).

`backend/tests/test_ib_web_client_order_guard.py` is broker-stub based: the
stub only records the irreversible `iserver_place_orders` endpoint.  It proves
**11 negative attempts** caused **0 submissions**:

- 4 shared-policy denials: halt, disallowed account, per-order cap, aggregate cap;
- 1 stale-Gateway denial;
- 5 malformed orders: unsafe ticker, invalid side, zero quantity, NaN price,
  and missing idempotency key;
- 1 duplicate-idempotency retry after a prior accepted submission (no second
  submission).

The one allowed Client Portal case produced **exactly 1** submission with the
expected account and payload (`AAPL`, `BUY`, 10.0 shares, `MKT`, `DAY`).  The
same test also source-audits the class to assert that the order endpoint has
only the guarded call site.

## Wider-suite note

The capped, durable project-venv full suite reached completion but has one
unrelated baseline failure: `backend/tests/test_ib_worker.py::test_ib_worker_calls_and_stays_connected`
expects a broker call while the hardened default Gateway posture is dormant.
It does not exercise `IBWebClient`; the relevant p3 guard suite above is green.
No live order, capital movement, or deployment occurred.
