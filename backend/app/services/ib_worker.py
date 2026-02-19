from __future__ import annotations

import asyncio
import os
import queue
import threading
import time
from concurrent.futures import Future
from typing import Any, Callable, TypeVar

from fastapi import HTTPException

from app.core.config import settings

T = TypeVar("T")


class _IbWorker:
    """
    A single background thread that owns the ib_insync.IB instance.

    Why: ib_insync requires its asyncio loop to be pumped to keep the socket alive.
    In sync FastAPI routes, the loop isn't running between requests, so IB Gateway
    will disconnect after ~1s. This worker continuously calls ib.sleep() and runs
    all IB operations serially via a task queue.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._q: queue.Queue[tuple[Callable[[Any], Any], Future[Any]]] = queue.Queue()

        self._ib: Any | None = None
        self._client_id: int | None = None

        # Connection settings (mutable at runtime).
        self._conn_host: str = settings.ib_host
        self._conn_port: int = int(settings.ib_port)
        self._conn_epoch: int = 0

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
        self._q.put((fn, fut))
        try:
            return fut.result(timeout=timeout)  # type: ignore[return-value]
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

    def _ensure_connected(self) -> Any:
        # ib_insync expects an event loop to exist in this thread, even at import time.
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

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
            return ib

        with self._lock:
            host = self._conn_host
            port = int(self._conn_port)

        readonly = not bool(settings.enable_live_trading)
        try:
            ib.connect(host, port, clientId=int(self._client_id), readonly=readonly, timeout=5)
            return ib
        except Exception:
            # Friendly fallback for Docker Desktop when people leave IB_HOST=127.0.0.1
            if host in {"127.0.0.1", "localhost"}:
                try:
                    ib.connect("host.docker.internal", port, clientId=int(self._client_id), readonly=readonly, timeout=5)
                    return ib
                except Exception:
                    pass
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Cannot connect to IB Gateway/TWS at {host}:{port}. "
                    "Ensure IB Gateway/TWS is running and API is enabled. "
                    "If IB runs on the host, set IB_HOST=host.docker.internal."
                ),
            )

    def get_connection_info(self) -> dict[str, Any]:
        with self._lock:
            return {"host": self._conn_host, "port": int(self._conn_port)}

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
        except Exception:
            # If anything goes wrong during pump, we will reconnect on next iteration.
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
        while not self._stop.is_set():
            # If connection settings changed, force a reconnect.
            with self._lock:
                epoch = self._conn_epoch
            if epoch != last_epoch:
                self._disconnect()
                last_epoch = epoch

            # Keep connection alive.
            try:
                self._ensure_connected()
            except HTTPException:
                # Connection down; wait a bit and retry
                time.sleep(0.5)

            # Process at most one task per loop so we pump frequently.
            try:
                fn, fut = self._q.get(timeout=0.05)
            except queue.Empty:
                self._pump()
                continue

            try:
                ib = self._ensure_connected()
                res = fn(ib)
                fut.set_result(res)
            except Exception as e:
                fut.set_exception(e)
            finally:
                self._pump()

        # Graceful shutdown
        self._disconnect()


_worker = _IbWorker()


def call_ib(fn: Callable[[Any], T], *, timeout: float = 10.0) -> T:
    return _worker.call(fn, timeout=timeout)


def configure_ib_connection(*, host: str, port: int) -> None:
    _worker.configure_connection(host=host, port=port)


def current_ib_connection() -> dict[str, Any]:
    return _worker.get_connection_info()


def stop_ib_worker() -> None:
    _worker.stop()

