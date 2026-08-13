# Alt-data coverage and reconstruction — literal h5 evidence

Captured 2026-08-13 from the repository root.  This receipt closes the two
evidence-format gaps identified by the h5 verifier; coverage facts remain in
[`altdata_coverage_audit.json`](altdata_coverage_audit.json), the release
manifest, and the datasheet.

## Manifest SHA-256 recalculation

```console
$ sha256sum exports/congress_pit/_manifest.json
3b63c268c464a35570de58917b074df90cbb86d7a35b9e2bcbf4bbf13abb3a81  exports/congress_pit/_manifest.json
```

This is the SHA-256 stated in the datasheet.  The manifest declares the
measured full-archive coverage as 31 complete days out of 32, retaining
2026-07-13 in the denominator and naming
`cftc_disaggregated_futures_cot` and
`house_periodic_transaction_report_index` as its missing sources.

## Adversarial reconstruction output

The required suite was executed exactly as follows:

```console
$ pytest backend/tests/test_altdata_reconstruction.py -v
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/servidor/Desktop/cursor-projects/ib_bot
configfile: pytest.ini
plugins: asyncio-1.4.0, anyio-4.13.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 2 items

backend/tests/test_altdata_reconstruction.py ..                          [100%]

=============================== warnings summary ===============================
../../../.local/lib/python3.12/site-packages/fastapi/testclient.py:1
  /home/servidor/.local/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

backend/app/main.py:67
  /home/servidor/Desktop/cursor-projects/ib_bot/backend/app/main.py:67: DeprecationWarning:
          on_event is deprecated, use lifespan event handlers instead.

          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).

    @app.on_event("startup")

../../../.local/lib/python3.12/site-packages/fastapi/applications.py:4681
../../../.local/lib/python3.12/site-packages/fastapi/applications.py:4681
  /home/servidor/.local/lib/python3.12/site-packages/fastapi/applications.py:4681: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.

          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).

    return self.router.on_event(event_type)  # ty: ignore[deprecated]

backend/app/main.py:86
  /home/servidor/Desktop/cursor-projects/ib_bot/backend/app/main.py:86: DeprecationWarning:
          on_event is deprecated, use lifespan event handlers instead.

          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).

    @app.on_event("shutdown")

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 2 passed, 5 warnings in 0.05s =========================
```

Expanded pytest output identifies the adversarial case that injects snapshot
2 captured after the reconstruction day; the test passes only because the
reconstructor raises the expected `ValueError` (`future vintage 2 captured on
2026-07-21`):

```console
$ pytest backend/tests/test_altdata_reconstruction.py -vv --tb=short
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.3, pluggy-1.6.0 -- /usr/bin/python3
cachedir: .pytest_cache
rootdir: /home/servidor/Desktop/cursor-projects/ib_bot
configfile: pytest.ini
plugins: asyncio-1.4.0, anyio-4.13.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 2 items

backend/tests/test_altdata_reconstruction.py::test_reconstructs_day_d_using_only_vintages_at_or_before_d PASSED [ 50%]
backend/tests/test_altdata_reconstruction.py::test_reconstruction_rejects_one_injected_future_vintage PASSED [100%]

======================== 2 passed, 5 warnings in 0.06s =========================
```
