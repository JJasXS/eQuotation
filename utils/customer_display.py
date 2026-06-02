"""Flatten SQL Accounting customer API / AR_CUSTOMER rows for create-quotation UI."""
from __future__ import annotations

from typing import Any


# Nested SQL API collections — branch rows are flattened separately.
_NESTED_COLLECTION_KEYS = frozenset(
    {
        "sdsbranch",
        "sdscreditcontrol",
        "sdsbankacc",
        "sdstariff",
        "addresses",
        "address",
    }
)

# Omit noisy / internal keys from the display list (still in customerScalars if needed).
_DISPLAY_SKIP_KEYS = frozenset({"dirty"})


def _humanize_field_key(key: str) -> str:
    s = str(key or "").strip()
    if not s:
        return ""
    if s.lower().startswith("udf_"):
        rest = s[4:].replace("_", " ").strip()
        return f"UDF {rest.title()}" if rest else "UDF"
    return s.replace("_", " ").strip().title()


def _format_scalar_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    s = str(value).strip()
    if s in ("----", "null", "None"):
        return ""
    return s


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def flatten_customer_record(
    source: dict[str, Any],
    *,
    branch_obj: dict[str, Any] | None = None,
    branch_label: str = "Billing branch",
) -> tuple[list[dict[str, str]], dict[str, str]]:
    """
    Build UI rows and a lowercase scalar map for salesquotation merge.

    Returns:
        display_fields: [{key, label, value}, ...]
        customer_scalars: {lowercase_key: string_value}
    """
    if not isinstance(source, dict):
        return [], {}

    scalars: dict[str, str] = {}
    rows: list[dict[str, str]] = []

    def add_row(key: str, label: str, raw: Any, *, store_scalar: bool = True) -> None:
        if key.lower() in _DISPLAY_SKIP_KEYS:
            return
        display = _format_scalar_value(raw)
        if store_scalar and _is_scalar(raw):
            scalars[str(key).lower()] = display
        rows.append({"key": key, "label": label, "value": display})

    priority = (
        "code",
        "companyname",
        "companyname2",
        "agent",
        "area",
        "creditterm",
        "attention",
        "phone1",
        "mobile",
    )

    def sort_key(item: tuple[str, Any]) -> tuple[int, str]:
        k = item[0].lower()
        try:
            pri = priority.index(k)
        except ValueError:
            pri = 100
        return (pri, k)

    for key, val in sorted(source.items(), key=sort_key):
        kl = str(key).lower()
        if kl in _NESTED_COLLECTION_KEYS:
            if isinstance(val, list):
                add_row(key, _humanize_field_key(key), f"({len(val)} item(s))", store_scalar=False)
            continue
        if not _is_scalar(val):
            continue
        add_row(key, _humanize_field_key(key), val)

    if isinstance(branch_obj, dict) and branch_obj:
        for bkey, bval in sorted(branch_obj.items(), key=lambda x: str(x[0]).lower()):
            if not _is_scalar(bval):
                continue
            full_key = f"branch.{bkey}"
            label = f"{branch_label} · {_humanize_field_key(bkey)}"
            add_row(full_key, label, bval)
            # Prefer billing branch for quotation header fields when master is empty.
            bl = str(bkey).lower()
            if bl in ("address1", "address2", "address3", "address4", "phone1", "mobile", "attention", "email", "country", "postcode", "city", "state", "fax1", "fax2"):
                if not scalars.get(bl):
                    scalars[bl] = _format_scalar_value(bval)

    # Stable sort: priority keys first, then label
    pri_order = {p: i for i, p in enumerate(priority)}

    def row_sort(r: dict[str, str]) -> tuple[int, str]:
        base = str(r.get("key") or "").split(".")[-1].lower()
        return (pri_order.get(base, 50), str(r.get("label") or "").lower())

    rows.sort(key=row_sort)
    return rows, scalars


def merge_legacy_customer_payload(
    legacy: dict[str, Any],
    *,
    display_fields: list[dict[str, str]],
    customer_scalars: dict[str, str],
) -> dict[str, Any]:
    """Attach full display list + scalar map to get_user_info JSON (keeps legacy uppercase keys)."""
    out = dict(legacy)
    out["displayFields"] = display_fields
    out["customerScalars"] = customer_scalars
    return out
