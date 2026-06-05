"""Purchase request header / line description normalization."""
from __future__ import annotations

import re
from typing import Any

DEFAULT_PR_HEADER_DESCRIPTION = "Purchase Request"

_PLACEHOLDER_LINE_DESC = re.compile(
    r"^Auto-selected from Overall Report",
    re.IGNORECASE,
)
_SPLIT_HEADER_DESC = re.compile(
    r"Split from\s+PR-",
    re.IGNORECASE,
)


def is_placeholder_pr_line_description(description: Any) -> bool:
    text = str(description or "").strip()
    if not text:
        return False
    return bool(_PLACEHOLDER_LINE_DESC.match(text))


def is_split_pr_header_description(description: Any) -> bool:
    text = str(description or "").strip()
    if not text:
        return False
    return bool(_SPLIT_HEADER_DESC.search(text))


def normalize_pr_header_description(description: Any) -> str:
    """User-facing PR header text — never show split metadata here."""
    text = str(description or "").strip()
    if not text or is_split_pr_header_description(text):
        return DEFAULT_PR_HEADER_DESCRIPTION
    return text


def resolve_pr_line_description(
    item_code: Any,
    stored_description: Any,
    *,
    catalog_description: Any = None,
) -> str:
    """Prefer ST_ITEM / catalog description over auto-generated placeholders."""
    code = str(item_code or "").strip()
    catalog = str(catalog_description or "").strip()
    stored = str(stored_description or "").strip()
    if catalog and (not stored or is_placeholder_pr_line_description(stored)):
        return catalog
    if stored and not is_placeholder_pr_line_description(stored):
        return stored
    if catalog:
        return catalog
    return code or stored


def lookup_st_item_descriptions(cur: Any, item_codes: list[str]) -> dict[str, str]:
    """Batch CODE → DESCRIPTION from ST_ITEM."""
    from utils.procurement_purchase_request import _get_table_columns, _pick_existing

    codes = [str(c or "").strip() for c in item_codes if str(c or "").strip()]
    if not codes or not cur:
        return {}
    cols = _get_table_columns(cur, "ST_ITEM")
    desc_col = _pick_existing(cols, "DESCRIPTION")
    if not desc_col:
        return {}
    placeholders = ", ".join(["?"] * len(codes))
    try:
        cur.execute(
            f"SELECT CODE, {desc_col} FROM ST_ITEM WHERE CODE IN ({placeholders})",
            tuple(codes),
        )
    except Exception:
        return {}
    out: dict[str, str] = {}
    for row in cur.fetchall() or []:
        if not row:
            continue
        code = str(row[0] or "").strip()
        desc = str(row[1] or "").strip() if len(row) > 1 else ""
        if code and desc:
            out[code] = desc
    return out


def persist_normalized_pr_header_description(
    cur: Any,
    request_dockey: int,
    source_description: Any = None,
) -> str:
    """Write normalized header DESCRIPTION on PH_PQ (primary + split child PRs)."""
    from utils.procurement_purchase_request import _get_table_columns, _pick_existing

    if not request_dockey:
        return DEFAULT_PR_HEADER_DESCRIPTION
    header_cols = _get_table_columns(cur, "PH_PQ")
    key_col = _pick_existing(header_cols, "DOCKEY", "PQKEY", "ID")
    desc_col = _pick_existing(header_cols, "DESCRIPTION", "JUSTIFICATION")
    if not key_col or not desc_col:
        return DEFAULT_PR_HEADER_DESCRIPTION

    current = source_description
    if current is None:
        cur.execute(
            f"SELECT {desc_col} FROM PH_PQ WHERE {key_col} = ?",
            (int(request_dockey),),
        )
        row = cur.fetchone()
        current = row[0] if row else ""

    normalized = normalize_pr_header_description(current)
    cur.execute(
        f"UPDATE PH_PQ SET {desc_col} = ? WHERE {key_col} = ?",
        (normalized[:500], int(request_dockey)),
    )
    return normalized


def refresh_placeholder_line_descriptions(
    cur: Any,
    request_dockey: int,
    detail_ids: list[int] | None = None,
) -> int:
    """Rewrite PH_PQDTL DESCRIPTION when it is an Overall Report placeholder."""
    from utils.procurement_purchase_request import _clean_text, _get_table_columns, _pick_existing

    if not request_dockey:
        return 0
    detail_cols = _get_table_columns(cur, "PH_PQDTL")
    fk_col = _pick_existing(detail_cols, "DOCKEY", "PQKEY", "REQUEST_ID", "HEADER_ID")
    dtl_col = _pick_existing(detail_cols, "DTLKEY", "PQDTLKEY", "ID")
    item_col = _pick_existing(detail_cols, "ITEMCODE", "ITEM_CODE")
    desc_col = _pick_existing(detail_cols, "DESCRIPTION", "ITEMNAME")
    if not fk_col or not dtl_col or not item_col or not desc_col:
        return 0

    if detail_ids:
        placeholders = ", ".join(["?"] * len(detail_ids))
        cur.execute(
            f"""
            SELECT {dtl_col}, {item_col}, {desc_col}
            FROM PH_PQDTL
            WHERE {fk_col} = ? AND {dtl_col} IN ({placeholders})
            """,
            tuple([int(request_dockey), *[int(x) for x in detail_ids]]),
        )
    else:
        cur.execute(
            f"""
            SELECT {dtl_col}, {item_col}, {desc_col}
            FROM PH_PQDTL
            WHERE {fk_col} = ?
            """,
            (int(request_dockey),),
        )

    rows = cur.fetchall() or []
    if not rows:
        return 0

    codes = [str(r[1] or "").strip() for r in rows if r and str(r[1] or "").strip()]
    catalog = lookup_st_item_descriptions(cur, codes)
    updated = 0
    for row in rows:
        if not row:
            continue
        dtl_id = int(row[0])
        code = str(row[1] or "").strip()
        stored = _clean_text(row[2])
        if not is_placeholder_pr_line_description(stored):
            continue
        resolved = resolve_pr_line_description(code, stored, catalog_description=catalog.get(code))
        if not resolved or resolved == stored:
            continue
        cur.execute(
            f"UPDATE PH_PQDTL SET {desc_col} = ? WHERE {dtl_col} = ?",
            (resolved[:255], dtl_id),
        )
        updated += 1
    return updated
