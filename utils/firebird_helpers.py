"""Shared Firebird / value helpers used across procurement and quotation modules.

Import from here instead of redefining locally. Underscore aliases are provided
for drop-in replacement of legacy ``_clean_text``-style private names.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def as_decimal(value: Any, default: str = "0") -> Decimal:
    try:
        raw = value if value is not None else default
        text = str(raw).replace(",", "").strip()
        return Decimal(text if text else default)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def to_float(value: Any, default: float = 0.0) -> float:
    """Coerce value to float; strips commas. Used as shared ``_num`` / ``_safe_float``."""
    if value is None or value == "":
        return float(default)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        return float(str(value).replace(",", "").strip() or default)
    except (TypeError, ValueError):
        return float(default)


def get_table_columns(cur: Any, table_name: str) -> set[str]:
    cur.execute(
        """
        SELECT TRIM(RF.RDB$FIELD_NAME)
        FROM RDB$RELATION_FIELDS RF
        WHERE RF.RDB$RELATION_NAME = ?
        """,
        (table_name.upper(),),
    )
    return {str(row[0]).strip().upper() for row in (cur.fetchall() or []) if row and row[0]}


def pick_existing(columns: set[str], *candidates: str) -> str:
    for name in candidates:
        if name.upper() in columns:
            return name.upper()
    return ""


def table_exists(cur: Any, table_name: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*)
        FROM RDB$RELATIONS
        WHERE RDB$SYSTEM_FLAG = 0
          AND TRIM(RDB$RELATION_NAME) = ?
        """,
        (table_name.upper(),),
    )
    row = cur.fetchone()
    return bool(row and int(row[0] or 0) > 0)


# Legacy private-name aliases (call sites can migrate gradually).
_clean_text = clean_text
_clean_str = clean_text
_as_decimal = as_decimal
_money = money
_to_float = to_float
_to_number = to_float
_safe_float = to_float
_num = to_float
_get_table_columns = get_table_columns
_pick_existing = pick_existing
_table_exists = table_exists
