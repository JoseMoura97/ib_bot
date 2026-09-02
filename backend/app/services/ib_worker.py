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
    """Thread-safe abandon/commit gate for ONE call_ib() invocation.

    concurrent.futures.Future.cancel() deliberately refuses to cancel a
    Future once it is RUNNING, so it cannot signal "the caller gave up" for a
    task already mid-execution on the worker thread (e.g. blocked inside a
    broker call that outlives the caller's timeout) -- exactly the case that
    let an abandoned closure reach ib.placeOrder() after its caller timed out
    waiting on reqAllOpenOrders(). A first version of this token fixed that
    with a plain is_abandoned() flag checked immediately before placeOrder --
    but "check, then act" is itself a TOCTOU race: the caller's timeout can
    mark the token abandoned in the gap between the check and the actual
    ib.placeOrder() call, so the check can read False and the order still go
    out for an already-abandoned caller (an independent ECC reviewer
    reproduced this without any network I/O, forcing the timeout into that
    exact gap).

    The fix is to make "may I proceed" and "the caller gave up" resolve on
    the SAME lock, as a single atomic transition with only two possible
    winners:

    - abandon() (called by the caller's thread on timeout) and try_commit()
      (called by the worker thread immediately before the irreversible
      action, with the action executed unconditionally right after a True
      return -- no further branching in between) both acquire ``_lock``.
    - Whichever runs first under the lock wins. If abandon() wins, it sets
      ``_abandoned`` while ``_committed`` is still False, so a subsequent
      try_commit() sees ``_abandoned`` and refuses (returns False) -- 0
      irreversible actions happen, ever, for that caller.
    - If try_commit() wins, it sets ``_committed`` before releasing the lock.
      A subsequent abandon() then sees ``_committed`` already True and
      returns False -- telling the caller its timeout raced an action that
      is now guaranteed to execute. That caller MUST treat the outcome as
      unknown/ambiguous (reconciliation required), never as a clean, side-
      effect-free timeout.

    Once abandoned, ``_abandoned`` stays True forever, so later legs in a
    multi-order basket also refuse to commit -- an abandoned caller gets no
    *further* orders placed even if an earlier one already went out before
    the abandonment was registered.
    """

    __slots__ = ("_lock", "_abandoned", "_committed")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._abandoned = False
        self._committed = False

    def abandon(self) -> bool:
        """Called by the caller's thread when call_ib(..., timeout=X) times
        out. Returns True iff this call is now guaranteed side-effect-free:
        no guarded irreversible action has committed and none ever will.
        Returns False iff a guarded action already committed under the lock
        -- its outcome is unknown to the caller and MUST be surfaced as an
        ambiguous, non-terminal, reconciliation-required failure, never
        treated as a clean/no-op timeout."""
        with self._lock:
            self._abandoned = True
            return not self._committed

    def try_commit(self) -> bool:
        """Called by the worker thread immediately before an irreversible
        broker action (e.g. placeOrder), with the action executed
        unconditionally right after a True return -- no read-then-act gap.
        Returns True iff the action may proceed (not yet abandoned).
        Returns False iff the caller already abandoned this call -- the
        action MUST be skipped."""
        with self._lock:
            if self._abandoned:
                return False
            self._committed = True
            return True

    def is_abandoned(self) -> bool:
        """Read-only snapshot. Safe for a cheap early-exit (e.g. skipping a
        still-queued task before it starts running) but NOT a substitute for
        try_commit() when gating an irreversible action -- reading this and
        then separately performing the action is exactly the TOCTOU this
        class exists to close."""
        with self._lock:
            return self._abandoned


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
            # The caller gave up waiting. fn may still be sitting in the
            # queue (skip it entirely), already mid-execution but not yet at
            # its irreversible action, or -- the race an ECC reviewer forced
            # -- may have ALREADY committed to that action a moment earlier.
            # abandon() and the guarded try_commit() contend on the same
            # lock, so exactly one of them wins:
            if not cancel_token.abandon():
                # try_commit() already won: an irreversible broker action
                # (e.g. placeOrder) is guaranteed to execute (or already has)
                # for a caller that is no longer waiting. This is NOT a
                # clean, side-effect-free timeout -- surface it as an
                # explicit, non-terminal, reconciliation-required failure so
                # nothing downstream can mistake it for "nothing happened".
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "reconciliation required: this call timed out AFTER an "
                        "irreversible broker action was already committed to "
                        "execute; its outcome is unknown and must be reconciled "
                        "against live broker state before any further action"
                    ),
                ) from None
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
        """Read-only: True if the caller of the call_ib() invocation
        currently executing on the worker thread has already timed out and
        given up. INFORMATIONAL ONLY -- do not use this to gate an
        irreversible broker action (e.g. placeOrder); reading this and then
        separately performing the action is a TOCTOU race. Use
        try_commit_active_call() instead, which is atomic.
        """
        token = self._active_cancel_token
        return bool(token is not None and token.is_abandoned())

    def try_commit_active_call(self) -> bool:
        """Atomically claim permission to perform ONE irreversible broker
        action (e.g. placeOrder) for the call_ib() invocation currently
        running on the worker thread, with the action executed
        unconditionally right after a True return -- no read-then-act gap.

        Returns True iff the action may proceed. Returns False iff the
        caller already abandoned this call (its timeout raced ahead) -- the
        action MUST be skipped. If there is no active call context (this was
        invoked outside any call_ib()-dispatched closure -- e.g. call_ib
        itself was replaced with a synchronous stub, as many tests do, so
        there is no cancellation-token machinery in play at all), there is
        no caller-timeout race to protect against: allow the action. This
        matches how a synchronously-stubbed call_ib can never time out.
        """
        token = self._active_cancel_token
        if token is None:
            return True
        return token.try_commit()

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
    """Read-only: True if the calling call_ib() invocation currently running
    on the worker thread has already timed out on its caller. INFORMATIONAL
    ONLY -- never use this to gate an irreversible broker action (e.g.
    placeOrder); reading this and then separately performing the action is a
    TOCTOU race (an independent ECC reviewer reproduced exactly this without
    any network I/O by forcing a timeout into that gap). Use
    call_try_commit() instead, which is atomic."""
    return _worker.is_active_call_abandoned()


def call_try_commit() -> bool:
    """Atomically claim permission to perform ONE irreversible broker action
    (e.g. placeOrder) for the call_ib() invocation currently running on the
    worker thread. Call this immediately before the action, with the action
    executed unconditionally right after a True return -- no read-then-act
    gap. Returns True iff the action may proceed. Returns False iff the
    caller already abandoned this call -- the action MUST be skipped; a
    caller that times out after this call committed will see its
    call_ib(...) raise an explicit reconciliation-required error instead of
    a clean timeout, so the ambiguity is never silently discarded."""
    return _worker.try_commit_active_call()


def configure_ib_connection(*, host: str, port: int) -> None:
    _worker.configure_connection(host=host, port=port)


def current_ib_connection() -> dict[str, Any]:
    return _worker.get_connection_info()


def stop_ib_worker() -> None:
    _worker.stop()

