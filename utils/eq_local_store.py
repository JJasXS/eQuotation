"""Process-shared SQLite helpers for OTP and email notification idempotency.

Uses a local file (not Firebird) so atomic locks work across threads and
uvicorn worker processes without changing SQL Accounting schema.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager

_LOCK = threading.Lock()
_INITIALIZED_PATHS: set[str] = set()


def local_store_path(filename: str = "eq_runtime_store.sqlite3") -> str:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    data_dir = os.getenv("EQ_RUNTIME_STORE_DIR") or os.path.join(root, "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, filename)


@contextmanager
def sqlite_connection(path: str | None = None):
    db_path = path or local_store_path()
    with _LOCK:
        if db_path not in _INITIALIZED_PATHS:
            _ensure_schema(db_path)
            _INITIALIZED_PATHS.add(db_path)
    con = sqlite3.connect(db_path, timeout=30, isolation_level=None)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=30000")
        yield con
    finally:
        con.close()


def _ensure_schema(db_path: str) -> None:
    con = sqlite3.connect(db_path, timeout=30, isolation_level=None)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS otp_store (
                otp_key TEXT PRIMARY KEY NOT NULL,
                otp_hash TEXT NOT NULL,
                expiry_unix REAL NOT NULL,
                last_sent_unix REAL,
                attempts INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS quotation_email_notify (
                dockey INTEGER NOT NULL,
                notify_type TEXT NOT NULL,
                status TEXT NOT NULL,
                reserved_at_unix REAL NOT NULL,
                updated_at_unix REAL NOT NULL,
                recipient TEXT,
                last_error TEXT,
                PRIMARY KEY (dockey, notify_type)
            );
            """
        )
    finally:
        con.close()
