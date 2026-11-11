"""Dedicated STA worker for SQLAcc.BizApp (out-of-proc LocalServer)."""
from __future__ import annotations

import concurrent.futures
import logging
import queue
import threading
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class StaWorkQueue:
    """
    Serialize COM work onto one apartment-threaded worker.

    ASP.NET/uvicorn callers are typically MTA; SQLAcc.BizApp must run on STA
    (same approach as sqlSign StaWorkQueue).
    """

    def __init__(self, *, name: str = "SqlAccSdk-STA") -> None:
        self._queue: queue.Queue[tuple[Callable[[], object], concurrent.futures.Future] | None] = (
            queue.Queue()
        )
        self._thread = threading.Thread(target=self._thread_main, name=name, daemon=True)
        self._started = threading.Event()
        self._closed = False
        self._thread.start()
        if not self._started.wait(timeout=10):
            raise RuntimeError("STA worker thread failed to start")

    def _thread_main(self) -> None:
        pythoncom = None
        init_error: BaseException | None = None
        try:
            import pythoncom as _pythoncom

            pythoncom = _pythoncom
            pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        except Exception as exc:
            init_error = exc
            logger.exception("STA worker could not CoInitializeEx")
        self._started.set()
        if init_error is not None:
            # Drain until close sentinel so run() callers get a clear error.
            while True:
                item = self._queue.get()
                if item is None:
                    break
                _func, fut = item
                fut.set_exception(
                    RuntimeError(f"STA worker failed to initialize COM: {init_error}")
                )
            return
        try:
            while True:
                item = self._queue.get()
                if item is None:
                    break
                func, fut = item
                if fut.cancelled():
                    continue
                try:
                    fut.set_result(func())
                except Exception as exc:
                    fut.set_exception(exc)
        finally:
            try:
                if pythoncom is not None:
                    pythoncom.CoUninitialize()
            except Exception:
                logger.debug("STA CoUninitialize failed", exc_info=True)

    def run(self, func: Callable[[], T], *, timeout_seconds: float = 120.0) -> T:
        if self._closed:
            raise RuntimeError("STA work queue is closed")
        fut: concurrent.futures.Future = concurrent.futures.Future()
        self._queue.put((func, fut))
        return fut.result(timeout=timeout_seconds)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        self._thread.join(timeout=5)
