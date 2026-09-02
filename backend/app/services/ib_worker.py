from __future__ import annotations

import asyncio
import os
import queue
import threading
import time
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, Callable, TypeVar

from fastapi import HTTPException

from app.core.config import settings

T = TypeVar("T")


class _CancelToken:
    """Thread-safe "the caller gave up" flag for one call_ib() invocation.

    concurrent.futures.Future.cancel() deliberately refuses to cancel a Future
    once it is RUNNING, so it cannot signal abandonment for a task that is
    already mid-execution on the worker thread (e.g. blocked inside a broker
    call that outlives the caller's timeout) -- exactly the case that let an
    abandoned closure reach ib.placeOrder() after its caller timed out waiting
    on reqAllOpenOrders(). This token is independent of the Future's state
    machine and can be set at any point, from any thread.
    """

    __slots__ = ("_event",)

    def __init__(self) -> None:
        self._event = threading.Event()

    def abandon(self) -> None:
        self._event.set()

    def is_abandoned(self) -> bool:
        return self._event.is_set()


class _IbWorker:
    """
    A single background thread that owns the ib_insync.IB instance.

    Why: ib_insync requires its asyncio loop to be pumped to keep the socket alive.
    In sync FastAPI routes, the loop isn't running between requests, so IB Gateway
    will disconnect after ~1s. This worker continuously calls ib.sleep() and runs
    all IB operations serially via a task queue.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        disconnect_alert_threshold_seconds: float | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._q: queue.Queue[tuple[Callable[[Any], Any], "Future[Any]", _CancelToken]] = queue.Queue()
        # Set by _run() only, for the duration of the currently-executing task,
        # so a closure running on the worker thread can consult
        # is_active_call_abandoned() / call_is_cancelled() immediately before an
        # irreversible broker action (e.g. placeOrder).
        self._active_cancel_token: _CancelToken | None = None

        self._ib: Any | None = None
        self._client_id: int | None = None

        # Connection settings (mutable at runtime).
        self._conn_host: str = settings.ib_host
        self._conn_port: int = int(settings.ib_port)
        self._conn_epoch: int = 0

        # Connection health is written only by this worker and exposed as a
        # snapshot. Keeping the clock injectable makes the outage policy fully
        # testable without waiting for the production 30-second threshold.
        self._clock = clock
        self._disconnect_alert_threshold_seconds = disconnect_alert_threshold_seconds
        self._connected = False
        self._last_connect_ok_at: float | None = None
        self._last_error: str | None = None
        self._consecutive_failures = 0
        self._outage_started_at: float | None = None
        self._outage_alert_sent = False

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="ib-worker", daemon=True)
            self._thread.start()

    def stop(self, *, timeout: float = 5.0) -> None:
        with self._lock:
            self._stop.set()
            t = self._thread
        if t:
            t.join(timeout=timeout)

    def call(self, fn: Callable[[Any], T], *, timeout: float = 10.0) -> T:
        self.start()
        fut: Future[Any] = Future()
        cancel_token = _CancelToken()
        self._q.put((fn, fut, cancel_token))
        try:
            return fut.result(timeout=timeout)  # type: ignore[return-value]
        except FuturesTimeoutError:
            # The caller gave up waiting. fn may still be sitting in the queue
            # (skip it entirely) or already mid-execution on the worker thread
            # (e.g. blocked inside a broker call) -- either way it must never
            # be allowed to reach the broker on this caller's behalf. Abandon
            # the token so _run()'s pre-dequeue check and any in-closure
            # call_is_cancelled() check both refuse to proceed.
            cancel_token.abandon()
            raise
        except Exception as e:
            # Preserve HTTPException raised within tasks
            if isinstance(e, HTTPException):
                raise
            raise

    def _get_client_id(self) -> int:
        raw = os.getenv("IB_CLIENT_ID")
        if raw is None or not str(raw).strip():
            # Keep it stable per-process (single worker thread)
            return (os.getpid() % 1000) * 1000 + 1
        try:
            return int(str(raw).strip())
        except Exception:
            return (os.getpid() % 1000) * 1000 + 1

    def _alert_threshold_seconds(self) -> float:
        if self._disconnect_alert_threshold_seconds is not None:
            return float(self._disconnect_alert_threshold_seconds)
        return float(settings.ib_gateway_disconnect_alert_seconds)

    def _record_connect_success(self) -> None:
        with self._lock:
            self._connected = True
            self._last_connect_ok_at = float(self._clock())
            self._last_error = None
            self._consecutive_failures = 0
            self._outage_started_at = None
            # A recovery starts a new outage episode, so the next prolonged
            # outage is allowed one alert.
            self._outage_alert_sent = False

    def _record_connect_failure(self, error: BaseException) -> None:
        now = float(self._clock())
        error_text = str(error) or type(error).__name__
        alert_payload: tuple[str, int, str] | None = None
        with self._lock:
            self._connected = False
            self._last_error = error_text
            self._consecutive_failures += 1
            if self._outage_started_at is None:
                self._outage_started_at = now
            elapsed = now - self._outage_started_at
            if not self._outage_alert_sent and elapsed >= self._alert_threshold_seconds():
                self._outage_alert_sent = True
                alert_payload = (self._conn_host, int(self._conn_port), error_text)

        if alert_payload is not None:
            from app.services.alerting import send_gateway_disconnected_alert

            host, port, message = alert_payload
            # Alert transport failures must never stop reconnecting. Marking the
            # outage as alerted before the call intentionally limits volume to
            # one attempt per outage episode.
            try:
                send_gateway_disconnected_alert(host=host, port=port, error=message)
            except Exception:
                pass

    def _ensure_connected(self) -> Any:
        # ib_insync expects an event loop to exist in this thread, even at import time.
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        try:
            try:
                from ib_insync import IB  # optional dependency
            except Exception as e:  # pragma: no cover
                raise HTTPException(
                    status_code=503,
                    detail=f"ib_insync import failed: {type(e).__name__}: {e}",
                ) from e

            if self._ib is None:
                self._ib = IB()
            if self._client_id is None:
                self._client_id = self._get_client_id()

            ib = self._ib
            try:
                connected = bool(getattr(ib, "isConnected")())
            except Exception:
                connected = False

            if connected:
                self._record_connect_success()
                return ib

            with self._lock:
                host = self._conn_host
                port = int(self._conn_port)

            readonly = not bool(settings.enable_live_trading)
            try:
                ib.connect(host, port, clientId=int(self._client_id), readonly=readonly, timeout=5)
            except Exception:
                # Friendly fallback for Docker Desktop when people leave IB_HOST=127.0.0.1
                if host in {"127.0.0.1", "localhost"}:
                    try:
                        ib.connect("host.docker.internal", port, clientId=int(self._client_id), readonly=readonly, timeout=5)
                    except Exception:
                        pass
                    else:
                        self._record_connect_success()
                        return ib
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"Cannot connect to IB Gateway/TWS at {host}:{port}. "
                        "Ensure IB Gateway/TWS is running and API is enabled. "
                        "If IB runs on the host, set IB_HOST=host.docker.internal."
                    ),
                )
            self._record_connect_success()
            return ib
        except Exception as exc:
            self._record_connect_failure(exc)
            raise

    def is_active_call_abandoned(self) -> bool:
        """True if the caller of the call_ib() invocation currently executing
        on the worker thread has already timed out and given up.

        Any code running inside a call_ib()-dispatched closure must check this
        immediately before an irreversible broker action (e.g. placeOrder) so
        an abandoned caller can never have an order placed on its behalf.
        """
        token = self._active_cancel_token
        return bool(token is not None and token.is_abandoned())

    def get_connection_info(self) -> dict[str, Any]:
        with self._lock:
            return {
                "host": self._conn_host,
                "port": int(self._conn_port),
                "connected": self._connected,
                "last_connect_ok_at": self._last_connect_ok_at,
                "last_error": self._last_error,
                "consecutive_failures": self._consecutive_failures,
            }

    def configure_connection(self, *, host: str, port: int) -> None:
        """
        Update IB connection target (host/port) at runtime.

        The worker thread will detect the change and reconnect using the new target.
        """
        host_s = str(host).strip()
        if not host_s:
            raise ValueError("host must be non-empty")
        port_i = int(port)
        if not (1 <= port_i <= 65535):
            raise ValueError("port must be in 1..65535")

        with self._lock:
            self._conn_host = host_s
            self._conn_port = port_i
            self._conn_epoch += 1

        # Ensure the worker is running so it can reconnect.
        self.start()

    def _disconnect(self) -> None:
        ib = self._ib
        if ib is None:
            return
        try:
            ib.disconnect()
        except Exception:
            pass

    def _pump(self) -> None:
        ib = self._ib
        if ib is None:
            return
        try:
            # Pump the asyncio loop & network traffic (keeps socket alive)
            ib.sleep(0.05)
        except Exception as exc:
            # If anything goes wrong during pump, we will reconnect on next iteration.
            self._record_connect_failure(exc)
            try:
                ib.disconnect()
            except Exception:
                pass

    def _run(self) -> None:
        # Ensure the worker thread always has an event loop for ib_insync.
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        last_epoch = -1
        _retry_delay = 0.5  # exponential backoff state for failed connections
        while not self._stop.is_set():
            # If connection settings changed, force a reconnect.
            with self._lock:
                epoch = self._conn_epoch
            if epoch != last_epoch:
                self._disconnect()
                last_epoch = epoch
                _retry_delay = 0.5  # reset backoff on explicit reconfigure

            # Keep connection alive.
            try:
                self._ensure_connected()
                _retry_delay = 0.5  # reset backoff on success
            except HTTPException:
                # Connection down; exponential backoff up to 30s to avoid log spam
                time.sleep(_retry_delay)
                _retry_delay = min(_retry_delay * 2, 30.0)

            # Process at most one task per loop so we pump frequently.
            try:
                fn, fut, cancel_token = self._q.get(timeout=0.05)
            except queue.Empty:
                self._pump()
                continue

            if cancel_token.is_abandoned():
                # The caller already timed out before we even dequeued this
                # task -- never execute it against the broker.
                self._pump()
                continue

            self._active_cancel_token = cancel_token
            try:
                ib = self._ensure_connected()
                res = fn(ib)
                fut.set_result(res)
            except Exception as e:
                fut.set_exception(e)
            finally:
                self._active_cancel_token = None
                self._pump()

        # Graceful shutdown
        self._disconnect()


_worker = _IbWorker()


def call_ib(fn: Callable[[Any], T], *, timeout: float = 10.0) -> T:
    return _worker.call(fn, timeout=timeout)


def call_is_cancelled() -> bool:
    """True if the calling call_ib() invocation currently running on the
    worker thread has already timed out on its caller. See
    _IbWorker.is_active_call_abandoned for why this cannot be expressed via
    the Future's own cancel() state machine."""
    return _worker.is_active_call_abandoned()


def configure_ib_connection(*, host: str, port: int) -> None:
    _worker.configure_connection(host=host, port=port)


def current_ib_connection() -> dict[str, Any]:
    return _worker.get_connection_info()


def stop_ib_worker() -> None:
    _worker.stop()

