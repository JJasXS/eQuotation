"""Shared helpers for purchase-request / transfer route handlers.

Promote nested ``def``s out of ``main.py`` route bodies so handlers stay flatter.
"""
from __future__ import annotations

from typing import Any

from utils.firebird_helpers import to_float
from utils.role_permissions import _truthy

# Re-export for call sites that used local ``_num``.
_num = to_float


def status_text(raw_status: Any) -> str:
    text = str(raw_status).strip().upper() if raw_status is not None else ""
    if text in {"DRAFT", "SUBMITTED", "APPROVED", "REJECTED", "CANCELLED"}:
        return text
    try:
        status_num = int(raw_status)
    except Exception:
        return text or "DRAFT"
    return {
        0: "DRAFT",
        1: "SUBMITTED",
        2: "APPROVED",
        3: "REJECTED",
        4: "CANCELLED",
    }.get(status_num, str(status_num))


_status_text = status_text


def fmt_date(raw: Any) -> str:
    if raw is None:
        return ""
    try:
        if hasattr(raw, "strftime"):
            return raw.strftime("%Y-%m-%d")
        if hasattr(raw, "isoformat"):
            return str(raw.isoformat())[:10]
        return str(raw).strip()[:10]
    except Exception:
        return str(raw or "").strip()[:10]


_fmt_date = fmt_date


def fb_text(value: Any) -> str:
    """Decode Firebird CHAR/BLOB values that arrive as bytes (avoid b'...' UI text)."""
    if value is None:
        return ""
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                return value.decode(enc).strip()
            except Exception:
                continue
        return bytes(value).decode("latin-1", errors="replace").strip()
    text = str(value).strip()
    if len(text) >= 3 and (
        (text.startswith("b'") and text.endswith("'"))
        or (text.startswith('b"') and text.endswith('"'))
    ):
        inner = text[2:-1]
        try:
            return bytes(inner, "utf-8").decode("unicode_escape").strip()
        except Exception:
            return inner.strip()
    return text


_fb_text = fb_text


def normalize_currency(value: Any) -> str:
    text = fb_text(value).upper()
    if not text or text in {"----", "-", "N/A", "NA", "NONE", "NULL"}:
        return "MYR"
    return text


_normalize_currency = normalize_currency


def to_bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) != 0
    return str(value).strip().lower() in ("1", "true", "t", "yes", "y")


_to_bool_or_none = to_bool_or_none


def resolve_supplier_master(selected_code: str, fallback_name: str = "") -> dict[str, Any]:
    code = str(selected_code or "").strip()
    if not code:
        return {}
    try:
        from utils.sql_api_supplier import (
            fetch_supplier_row_by_code,
            supplier_master_document_fields,
        )

        row = fetch_supplier_row_by_code(code)
        if row:
            return supplier_master_document_fields(row)
    except Exception:
        pass
    name = str(fallback_name or "").strip()
    return {"code": code, "companyname": name or code}


_resolve_supplier_master = resolve_supplier_master

# Re-export role_permissions truthy under the nested-def name used in transfer-candidates.
__all__ = [
    "_num",
    "_status_text",
    "_truthy",
    "_fmt_date",
    "_fb_text",
    "_normalize_currency",
    "_to_bool_or_none",
    "_resolve_supplier_master",
]
