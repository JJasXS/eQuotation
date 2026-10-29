"""Shared OTP storage with process-safe attempt limits and one-time use."""
from __future__ import annotations

import hashlib
import hmac
import os
import threading
from datetime import datetime
from typing import Any

from utils.eq_local_store import sqlite_connection

_MEM_LOCK = threading.RLock()
_MEMORY: dict[str, dict[str, Any]] = {}


def _use_sqlite() -> bool:
    """Default: sqlite when EQ_OTP_STORE=sqlite or multi-process hint; else memory+lock.

    Memory+lock is correct for the default single uvicorn process + a2wsgi threads.
    Set EQ_OTP_STORE=sqlite when running multiple OS processes.
    """
    mode = (os.getenv("EQ_OTP_STORE") or "").strip().lower()
    if mode in ("sqlite", "db", "shared"):
        return True
    if mode in ("memory", "mem", "process"):
        return False
    # Auto: prefer sqlite so restarts / accidental multi-process still share state.
    return True


def _hash_otp(otp: str) -> str:
    secret = (os.getenv("FLASK_SECRET_KEY") or "eq-otp-dev").encode("utf-8")
    return hmac.new(secret, str(otp).encode("utf-8"), hashlib.sha256).hexdigest()


def _row_to_dict(row) -> dict[str, Any]:
    return {
        "otp_hash": row["otp_hash"],
        "expiry": datetime.fromtimestamp(float(row["expiry_unix"])),
        "last_sent": datetime.fromtimestamp(float(row["last_sent_unix"])) if row["last_sent_unix"] else None,
        "attempts": int(row["attempts"] or 0),
    }


def get_otp(otp_key: str) -> dict[str, Any] | None:
    if not _use_sqlite():
        with _MEM_LOCK:
            data = _MEMORY.get(otp_key)
            return dict(data) if data else None
    with sqlite_connection() as con:
        cur = con.execute("SELECT * FROM otp_store WHERE otp_key = ?", (otp_key,))
        row = cur.fetchone()
        return _row_to_dict(row) if row else None


def put_otp(otp_key: str, otp: str, expiry: datetime, last_sent: datetime, attempts: int = 0) -> None:
    payload = {
        "otp_hash": _hash_otp(otp),
        "otp": otp,  # memory-only plaintext for verify; sqlite stores hash only
        "expiry": expiry,
        "last_sent": last_sent,
        "attempts": int(attempts or 0),
    }
    if not _use_sqlite():
        with _MEM_LOCK:
            _MEMORY[otp_key] = payload
        return
    with sqlite_connection() as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            con.execute(
                """
                INSERT INTO otp_store (otp_key, otp_hash, expiry_unix, last_sent_unix, attempts)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(otp_key) DO UPDATE SET
                    otp_hash=excluded.otp_hash,
                    expiry_unix=excluded.expiry_unix,
                    last_sent_unix=excluded.last_sent_unix,
                    attempts=excluded.attempts
                """,
                (
                    otp_key,
                    payload["otp_hash"],
                    expiry.timestamp(),
                    last_sent.timestamp() if last_sent else None,
                    int(attempts or 0),
                ),
            )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise


def delete_otp(otp_key: str) -> None:
    if not _use_sqlite():
        with _MEM_LOCK:
            _MEMORY.pop(otp_key, None)
        return
    with sqlite_connection() as con:
        con.execute("DELETE FROM otp_store WHERE otp_key = ?", (otp_key,))


def verify_and_consume(
    otp_key: str,
    otp: str,
    *,
    max_attempts: int,
) -> tuple[bool, str, dict[str, Any]]:
    """Atomically validate OTP.

    Returns (ok, error_code, meta) where error_code is '' on success or
    'missing' | 'expired' | 'locked' | 'invalid'.
    """
    now = datetime.now()
    if not _use_sqlite():
        with _MEM_LOCK:
            stored = _MEMORY.get(otp_key)
            if not stored:
                return False, "missing", {}
            if now > stored["expiry"]:
                _MEMORY.pop(otp_key, None)
                return False, "expired", {}
            attempts = int(stored.get("attempts") or 0)
            if attempts >= max_attempts:
                _MEMORY.pop(otp_key, None)
                return False, "locked", {}
            expected = stored.get("otp")
            if expected is None:
                # hash-only fallback
                if not hmac.compare_digest(stored.get("otp_hash") or "", _hash_otp(otp)):
                    stored["attempts"] = attempts + 1
                    if stored["attempts"] >= max_attempts:
                        _MEMORY.pop(otp_key, None)
                        return False, "locked", {"remaining": 0}
                    remaining = max_attempts - stored["attempts"]
                    return False, "invalid", {"remaining": remaining}
            elif not hmac.compare_digest(str(expected), str(otp)):
                stored["attempts"] = attempts + 1
                if stored["attempts"] >= max_attempts:
                    _MEMORY.pop(otp_key, None)
                    return False, "locked", {"remaining": 0}
                remaining = max_attempts - stored["attempts"]
                return False, "invalid", {"remaining": remaining}
            _MEMORY.pop(otp_key, None)
            return True, "", {}

    with sqlite_connection() as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            cur = con.execute("SELECT * FROM otp_store WHERE otp_key = ?", (otp_key,))
            row = cur.fetchone()
            if not row:
                con.execute("COMMIT")
                return False, "missing", {}
            if now.timestamp() > float(row["expiry_unix"]):
                con.execute("DELETE FROM otp_store WHERE otp_key = ?", (otp_key,))
                con.execute("COMMIT")
                return False, "expired", {}
            attempts = int(row["attempts"] or 0)
            if attempts >= max_attempts:
                con.execute("DELETE FROM otp_store WHERE otp_key = ?", (otp_key,))
                con.execute("COMMIT")
                return False, "locked", {}
            if not hmac.compare_digest(str(row["otp_hash"]), _hash_otp(otp)):
                attempts += 1
                if attempts >= max_attempts:
                    con.execute("DELETE FROM otp_store WHERE otp_key = ?", (otp_key,))
                    con.execute("COMMIT")
                    return False, "locked", {"remaining": 0}
                con.execute(
                    "UPDATE otp_store SET attempts = ? WHERE otp_key = ?",
                    (attempts, otp_key),
                )
                con.execute("COMMIT")
                return False, "invalid", {"remaining": max_attempts - attempts}
            con.execute("DELETE FROM otp_store WHERE otp_key = ?", (otp_key,))
            con.execute("COMMIT")
            return True, "", {}
        except Exception:
            con.execute("ROLLBACK")
            raise


def clear_all_for_tests() -> None:
    with _MEM_LOCK:
        _MEMORY.clear()
    if _use_sqlite():
        with sqlite_connection() as con:
            con.execute("DELETE FROM otp_store")
