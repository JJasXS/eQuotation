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
    "UDF_WEIGHT",
    "UDF_THICKNESS",
    "UDF_WIDTH",
    "UDF_LENGTH",
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


def fetch_stock_item_prices_for_chat(cur: Any) -> list[dict[str, Any]]:
    """
    Rows shaped for chat / legacy UI: CODE, DESCRIPTION, STOCKVALUE (from UDF_STDPRICE).
    Used when the catalog does not expose prices and chat needs a price list from Firebird.
    """
    cur.execute(
        """
        SELECT TRIM(RF.RDB$FIELD_NAME)
        FROM RDB$RELATION_FIELDS RF
        WHERE RF.RDB$RELATION_NAME = 'ST_ITEM'
        """
    )
    existing_columns = {_clean_str(row[0]) for row in (cur.fetchall() or []) if row and row[0]}
    if "UDF_STDPRICE" not in existing_columns:
        return []

    cur.execute(
        """
        SELECT CODE, DESCRIPTION, UDF_STDPRICE
        FROM ST_ITEM
        WHERE UDF_STDPRICE IS NOT NULL AND UDF_STDPRICE > 0
        """
    )
    rows = cur.fetchall() or []
    out: list[dict[str, Any]] = []
    for row in rows:
        code = _clean_str(row[0] if len(row) > 0 else None)
        desc = _clean_str(row[1] if len(row) > 1 else None)
        val = row[2] if len(row) > 2 else None
        if not desc:
            continue
        out.append({"CODE": code, "DESCRIPTION": desc, "STOCKVALUE": val})
    return out


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
    for col in sorted(existing_columns):
        if col.upper().startswith("UDF_") and col not in selected_columns:
            selected_columns.append(col)

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


def get_st_item_quotation_display_fields(cur: Any, item_code: str) -> dict[str, str]:
    """All ST_ITEM ``UDF_*`` columns for quotation lines (camelCase keys for the UI)."""
    from utils.stock_items_catalog import _udf_camel_case

    code = _clean_str(item_code)
    if not code:
        return {}
    cur.execute(
        """
        SELECT TRIM(RF.RDB$FIELD_NAME)
        FROM RDB$RELATION_FIELDS RF
        WHERE RF.RDB$RELATION_NAME = 'ST_ITEM'
        """
    )
    existing = sorted(
        {_clean_str(row[0]).upper() for row in (cur.fetchall() or []) if row and row[0]}
    )
    udf_cols = [c for c in existing if c.startswith("UDF_")]
    if not udf_cols:
        return {}
    sql_cols = ", ".join(udf_cols)
    cur.execute(f"SELECT {sql_cols} FROM ST_ITEM WHERE CODE = ?", (code,))
    row = cur.fetchone()
    if not row:
        return {}
    out: dict[str, str] = {}
    for idx, col in enumerate(udf_cols):
        val = row[idx]
        js_key = _udf_camel_case(col)
        if val is None:
            out[js_key] = ""
        elif isinstance(val, str):
            out[js_key] = val.strip()
        else:
            out[js_key] = str(val).strip()
    return out


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
