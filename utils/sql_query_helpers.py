"""Reusable SQL query helpers for Flask routes in main.py."""
from __future__ import annotations

from typing import Any


ST_ITEM_WANTED_COLUMNS = [
    "CODE",
    "DESCRIPTION",
    "STOCKGROUP",
    "REMARK1",
    "REMARK2",
    "UDF_STDPRICE",
    "UDF_MOQ",
    "UDF_DLEADTIME",
    "UDF_BUNDLE",
]


def _clean_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def find_customer_code_by_email(cur: Any, user_email: str) -> str | None:
    """Return AR_CUSTOMERBRANCH code for email, if found."""
    cur.execute("SELECT FIRST 1 CODE FROM AR_CUSTOMERBRANCH WHERE EMAIL = ?", (user_email,))
    row = cur.fetchone()
    if row and row[0]:
        return _clean_str(row[0])
    return None


def has_user_draft_orders(cur: Any, user_email: str, customer_code: str) -> bool:
    """Return whether user has any DRAFT order for the given customer code."""
    cur.execute(
        """
        SELECT COUNT(*) FROM ORDER_TPL o
        INNER JOIN CHAT_TPL c ON o.CHATID = c.CHATID
        WHERE c.USEREMAIL = ? AND o.STATUS = ? AND o.CUSTOMERCODE = ?
        """,
        (user_email, "DRAFT", customer_code),
    )
    row = cur.fetchone()
    count = row[0] if row and len(row) > 0 else 0
    return int(count or 0) > 0


def find_draft_order_id_by_chatid(cur: Any, chatid: str) -> int | None:
    """Return draft ORDERID for chat when present."""
    cur.execute("SELECT ORDERID FROM ORDER_TPL WHERE CHATID = ? AND STATUS = ?", (chatid, "DRAFT"))
    row = cur.fetchone()
    if row and row[0] is not None:
        return int(row[0])
    return None


def fetch_stock_items(cur: Any, wanted_columns: list[str] | None = None) -> list[dict[str, Any]]:
    """Fetch stock items with only columns existing in ST_ITEM."""
    selected_wanted_columns = wanted_columns or ST_ITEM_WANTED_COLUMNS

    cur.execute(
        """
        SELECT TRIM(RF.RDB$FIELD_NAME)
        FROM RDB$RELATION_FIELDS RF
        WHERE RF.RDB$RELATION_NAME = 'ST_ITEM'
        """
    )
    existing_columns = {_clean_str(row[0]) for row in (cur.fetchall() or []) if row and row[0]}
    selected_columns = [col for col in selected_wanted_columns if col in existing_columns]

    if not selected_columns:
        raise ValueError("No expected columns found in ST_ITEM")

    sql = f"SELECT {', '.join(selected_columns)} FROM ST_ITEM"
    cur.execute(sql)
    rows = cur.fetchall() or []

    items = []
    for row in rows:
        item = {}
        for idx, col in enumerate(selected_columns):
            val = row[idx]
            item[col] = _clean_str(val) if isinstance(val, str) else val
        items.append(item)

    return items


def get_st_item_udf_stdprice(cur: Any, item_code: str) -> float | None:
    """Return ST_ITEM.UDF_STDPRICE for item code when available."""
    cur.execute("SELECT UDF_STDPRICE FROM ST_ITEM WHERE CODE = ?", (item_code,))
    row = cur.fetchone()
    if row and row[0] is not None:
        try:
            return float(row[0])
        except Exception:
            return None
    return None


def find_price_seed_item(cur: Any, description: str) -> dict[str, Any] | None:
    """Find best seed item row used by pricing flow from ST_ITEM."""
    cur.execute(
        """
        SELECT FIRST 1 CODE, DESCRIPTION, UDF_STDPRICE
        FROM ST_ITEM
        WHERE UPPER(TRIM(DESCRIPTION)) = UPPER(?)
        """,
        (description,),
    )
    row = cur.fetchone()

    if not row and len(description) <= 30:
        cur.execute(
            """
            SELECT FIRST 1 CODE, DESCRIPTION, UDF_STDPRICE
            FROM ST_ITEM
            WHERE UPPER(TRIM(CODE)) = UPPER(?)
            """,
            (description,),
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        "CODE": _clean_str(row[0] if len(row) > 0 else None),
        "DESCRIPTION": _clean_str(row[1] if len(row) > 1 else None),
        "UDF_STDPRICE": row[2] if len(row) > 2 else None,
    }
