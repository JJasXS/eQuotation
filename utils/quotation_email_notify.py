"""Atomic quotation email notification reservation (cross-process safe)."""
from __future__ import annotations

import time
from typing import Any

from utils.eq_local_store import sqlite_connection

NOTIFY_PENDING_APPROVAL = "pending_approval"
# Stale pending reservations can be retried after this many seconds.
PENDING_STALE_SECONDS = 300.0


def reserve_notification(dockey: int, notify_type: str = NOTIFY_PENDING_APPROVAL) -> dict[str, Any]:
    """Atomically reserve a notification slot before sending mail.

    Returns:
      status: 'reserved' | 'already_sent' | 'in_progress'
    """
    dockey = int(dockey)
    now = time.time()
    with sqlite_connection() as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            cur = con.execute(
                "SELECT status, reserved_at_unix FROM quotation_email_notify WHERE dockey=? AND notify_type=?",
                (dockey, notify_type),
            )
            row = cur.fetchone()
            if row:
                status = str(row["status"] or "")
                reserved_at = float(row["reserved_at_unix"] or 0)
                if status == "sent":
                    con.execute("COMMIT")
                    return {"ok": True, "status": "already_sent"}
                if status == "pending" and (now - reserved_at) < PENDING_STALE_SECONDS:
                    con.execute("COMMIT")
                    return {"ok": True, "status": "in_progress"}
                # failed or stale pending → reclaim
                con.execute(
                    """
                    UPDATE quotation_email_notify
                    SET status='pending', reserved_at_unix=?, updated_at_unix=?, last_error=NULL
                    WHERE dockey=? AND notify_type=?
                    """,
                    (now, now, dockey, notify_type),
                )
                con.execute("COMMIT")
                return {"ok": True, "status": "reserved", "reclaimed": True}

            con.execute(
                """
                INSERT INTO quotation_email_notify
                    (dockey, notify_type, status, reserved_at_unix, updated_at_unix, recipient, last_error)
                VALUES (?, ?, 'pending', ?, ?, NULL, NULL)
                """,
                (dockey, notify_type, now, now),
            )
            con.execute("COMMIT")
            return {"ok": True, "status": "reserved"}
        except Exception:
            con.execute("ROLLBACK")
            raise


def mark_sent(dockey: int, recipient: str = "", notify_type: str = NOTIFY_PENDING_APPROVAL) -> None:
    now = time.time()
    with sqlite_connection() as con:
        con.execute(
            """
            UPDATE quotation_email_notify
            SET status='sent', updated_at_unix=?, recipient=?, last_error=NULL
            WHERE dockey=? AND notify_type=?
            """,
            (now, (recipient or "")[:320], int(dockey), notify_type),
        )


def mark_failed(dockey: int, error: str = "", notify_type: str = NOTIFY_PENDING_APPROVAL) -> None:
    now = time.time()
    with sqlite_connection() as con:
        con.execute(
            """
            UPDATE quotation_email_notify
            SET status='failed', updated_at_unix=?, last_error=?
            WHERE dockey=? AND notify_type=?
            """,
            (now, (error or "")[:500], int(dockey), notify_type),
        )


def get_status(dockey: int, notify_type: str = NOTIFY_PENDING_APPROVAL) -> dict[str, Any] | None:
    with sqlite_connection() as con:
        cur = con.execute(
            "SELECT * FROM quotation_email_notify WHERE dockey=? AND notify_type=?",
            (int(dockey), notify_type),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def clear_for_tests() -> None:
    with sqlite_connection() as con:
        con.execute("DELETE FROM quotation_email_notify")
