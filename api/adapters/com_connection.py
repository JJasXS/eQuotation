"""Reusable COM connection handler for SQL Account."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

try:
    import pythoncom
    import pywintypes
    import win32com.client
except ImportError:  # pragma: no cover - depends on Windows COM runtime
    pythoncom = None
    pywintypes = None
    win32com = None


class COMConnectionError(Exception):
    """Raised when COM connection cannot be created."""


def _format_com_error(exc: Exception) -> str:
    """Extract a readable message from COM exceptions."""
    if pywintypes is not None and isinstance(exc, pywintypes.com_error):
        details = []
        if len(exc.args) > 0 and exc.args[0]:
            details.append(str(exc.args[0]))
        if len(exc.args) > 1 and exc.args[1]:
            details.append(str(exc.args[1]))
        if len(exc.args) > 2 and exc.args[2]:
            details.append(str(exc.args[2]))
        return " | ".join(details) if details else str(exc)
    return str(exc)


class COMConnectionHandler:
    """Create and manage SQL Account COM sessions."""

    def __init__(self, prog_id: str | None = None) -> None:
        self.prog_id = prog_id or os.getenv("SQLACC_COM_PROG_ID", "SQLAcc.BizApp")

    @contextmanager
    def session(self) -> Generator[object, None, None]:
        """
        Open a COM session and release COM apartment correctly.

        Yields:
            COM biz app object for SQL Account.
        """
        if pythoncom is None or win32com is None:
            raise COMConnectionError(
                "pywin32 is not available. Install with 'pip install pywin32'."
            )

        pythoncom.CoInitialize()
        try:
            biz = win32com.client.Dispatch(self.prog_id)
            yield biz
        except Exception as exc:
            raise COMConnectionError(
                f"Unable to initialize COM object '{self.prog_id}': {_format_com_error(exc)}"
            ) from exc
        finally:
            pythoncom.CoUninitialize()
