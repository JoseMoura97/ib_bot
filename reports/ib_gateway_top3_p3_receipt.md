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
/home/servidor/Desktop/cursor-projects/ib_bot/.venv/bin/python -m pytest -q -p no:warnings \
  backend/tests/test_ib_web_client_order_guard.py \
  backend/tests/test_live_order_guard_bypass.py \
  backend/tests/test_ib_gateway_state_guard.py
```

Result on the p1-integrated tree: **32 passed**, 0 failed (exit 0).  The two
extra cases versus the isolated base are p1's healthy-to-disconnected and
healthy-to-stale transition regressions, now merged in.

`backend/tests/test_ib_web_client_order_guard.py` is broker-stub based: the
stub only records the irreversible `iserver_place_orders` endpoint.  It proves
**11 negative attempts** reached **0 broker**-stub submissions:

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

The earlier isolated run of this branch had one unrelated baseline failure,
`backend/tests/test_ib_worker.py::test_ib_worker_calls_and_stays_connected`,
which expected a broker call while the hardened default Gateway posture is
dormant.  That precondition was repaired on `main` at `967acf5` and is now
merged into this branch, so the failure is gone.

Full backend regression on the integrated tree, run from `backend/`:

```bash
/home/servidor/Desktop/cursor-projects/ib_bot/.venv/bin/python -m pytest tests/ \
  -p no:warnings \
  --ignore=tests/test_edgar_13f_fallback.py \
  --ignore=tests/test_plot_data_cache.py \
  --ignore=tests/test_rebalancing_engine_regressions.py \
  --ignore=tests/test_altdata_chain.py
```

Result: **221 passed, 17 skipped** (exit 0) on the phase worktree.

**Correction (DM, 2026-09-15, WEST):** the four `--ignore` exclusions above are
NOT justified.  `.cursorrules` documents pre-existing repo-root import errors for
only three of them (`test_edgar_13f_fallback`, `test_plot_data_cache`,
`test_rebalancing_engine_regressions`) and that note is stale — when the suite is
run from `backend/` with the repository venv, all four modules collect and pass.
The un-ignored integrated result is recorded in the next section and supersedes
this exclusion list.

No live Gateway socket, real broker, live order, capital movement, restart or
deployment occurred: `ibgateway` and `xvfb-ibgw` were `inactive` and IB API
ports 4001/4002 unbound throughout.  Every submission in these tests lands in
an in-process `_BrokerStub`, never in `ibind`.

## Integrated `main` regression (all three phases merged)

Merge commit `e3e7422` on `main` carries p1 + p2 + p3 together (p1 and p3 via
`62cff08`/`3d54a3a`, p2 via `e3e7422`).  Run from `backend/` with **no
`--ignore` exclusions**:

```bash
/home/servidor/Desktop/cursor-projects/ib_bot/.venv/bin/python -m pytest tests/ -p no:warnings
```

Result: **308 passed, 17 skipped, 0 failed** in 92.27s (exit 0), verified by the
Domain Manager on the merged `main` tree (2026-09-15, WEST).  The four modules
the older block excluded all collect and pass at this SHA.

This phase's named suite re-run at `main` after the p2 merge-back, from
`backend/`:

```bash
/home/servidor/Desktop/cursor-projects/ib_bot/.venv/bin/python -m pytest \
  tests/test_ib_web_client_order_guard.py tests/test_live_order_guard_bypass.py \
  tests/test_ib_gateway_state_guard.py -p no:warnings
```

Result: **32 passed** (exit 0) — the 11 negative bypass attempts still reach
**0 broker**-stub submissions and the one allowed case still produces
**exactly 1**.  `ibgateway` and `xvfb-ibgw` were `inactive` and IB API ports
4001/4002 unbound for the whole run — no live socket, broker call, order,
capital movement or deployment.
