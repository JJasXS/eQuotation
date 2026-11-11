"""PR → PO transfer completion for Admin/Staff active list filtering.

A purchase request is fully transferred when:
- at least one ST_XTRANS PQ→PO link exists for the header, and
- no transferable detail line still has remaining quantity.

Records are never deleted; fully transferred PRs are only omitted from active
APPROVED lists / counts. Partial and never-transferred PRs stay visible.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from utils.firebird_helpers import _as_decimal, _get_table_columns, _pick_existing


def _xtrans_quantity_expr(xtrans_cols: set[str]) -> str:
    qty_col = _pick_existing(xtrans_cols, "QTY")
    sqty_col = _pick_existing(xtrans_cols, "SQTY")
    suom_col = _pick_existing(xtrans_cols, "SUOMQTY")
    if suom_col and sqty_col and qty_col:
        return (
            f"COALESCE(NULLIF({suom_col}, 0), NULLIF({sqty_col}, 0), COALESCE({qty_col}, 0), 0)"
        )
    if sqty_col and qty_col:
        return f"COALESCE(NULLIF({sqty_col}, 0), COALESCE({qty_col}, 0), 0)"
    return suom_col or sqty_col or qty_col or "0"


def _truthy_sql_flag(column_ref: str) -> str:
    """Firebird-safe truthy check for SMALLINT/CHAR/BOOLEAN flags."""
    return (
        f"CAST({column_ref} AS VARCHAR(16)) IN "
        f"('1', 'T', 'TRUE', 'Y', 'YES', 'true', 'True')"
    )


def _line_is_transferable_sql(
    *,
    detail_alias: str = "D",
    header_alias: str = "H",
    detail_transferable_col: str | None,
    detail_approved_col: str | None,
    header_transferable_col: str | None,
) -> str:
    """Match transfer-candidates transferable rules (SQL fragment, no params)."""
    parts: list[str] = ["1 = 1"]
    if header_transferable_col:
        # Missing/NULL header transferable treated as allowed (same as list UI defaults).
        parts.append(
            f"({header_alias}.{header_transferable_col} IS NULL OR "
            f"{_truthy_sql_flag(f'{header_alias}.{header_transferable_col}')})"
        )
    if detail_transferable_col and detail_approved_col:
        parts.append(
            f"("
            f"{_truthy_sql_flag(f'{detail_alias}.{detail_transferable_col}')}"
            f" OR {_truthy_sql_flag(f'{detail_alias}.{detail_approved_col}')}"
            f")"
        )
    elif detail_transferable_col:
        parts.append(
            f"({detail_alias}.{detail_transferable_col} IS NULL OR "
            f"{_truthy_sql_flag(f'{detail_alias}.{detail_transferable_col}')})"
        )
    return " AND ".join(parts)


def sql_pr_fully_transferred_predicate(
    cur: Any,
    *,
    header_alias: str = "H",
    header_key_col: str = "DOCKEY",
) -> str:
    """
    SQL boolean expression: header is fully transferred to PO.

    Safe to AND as ``NOT ({expr})`` for active APPROVED lists.
    Returns ``0 = 1`` when schema cannot support the check (never hide).
    """
    key = str(header_key_col or "").strip()
    if not key:
        return "0 = 1"

    detail_cols = _get_table_columns(cur, "PH_PQDTL")
    xtrans_cols = _get_table_columns(cur, "ST_XTRANS")
    if not detail_cols or not xtrans_cols:
        return "0 = 1"

    d_key = _pick_existing(detail_cols, "DTLKEY", "ID")
    d_fk = _pick_existing(detail_cols, "DOCKEY", "PQKEY", "REQUEST_ID", "HEADER_ID")
    d_qty = _pick_existing(detail_cols, "QTY")
    d_transferable = _pick_existing(detail_cols, "TRANSFERABLE")
    d_approved = _pick_existing(detail_cols, "UDF_PQAPPROVED")
    x_fromdoc = _pick_existing(xtrans_cols, "FROMDOCTYPE")
    x_fromkey = _pick_existing(xtrans_cols, "FROMDOCKEY")
    x_fromdtl = _pick_existing(xtrans_cols, "FROMDTLKEY")
    if not (d_key and d_fk and d_qty and x_fromdoc and x_fromkey and x_fromdtl):
        return "0 = 1"

    header_cols = _get_table_columns(cur, "PH_PQ")
    h_transferable = _pick_existing(header_cols, "TRANSFERABLE")
    qty_expr = _xtrans_quantity_expr(xtrans_cols)
    line_ok = _line_is_transferable_sql(
        detail_alias="D",
        header_alias=header_alias,
        detail_transferable_col=d_transferable,
        detail_approved_col=d_approved,
        header_transferable_col=h_transferable,
    )

    has_transfer = (
        f"EXISTS ("
        f"SELECT 1 FROM ST_XTRANS X "
        f"WHERE X.{x_fromkey} = {header_alias}.{key} "
        f"AND TRIM(UPPER(COALESCE(X.{x_fromdoc}, ''))) IN ('PQ', 'PH_PQ')"
        f")"
    )
    has_remaining = (
        f"EXISTS ("
        f"SELECT 1 FROM PH_PQDTL D "
        f"LEFT JOIN ("
        f"  SELECT {x_fromkey} AS FROMDOCKEY, {x_fromdtl} AS FROMDTLKEY, "
        f"         CAST(SUM(CAST({qty_expr} AS DOUBLE PRECISION)) AS DOUBLE PRECISION) AS TRANSFERRED_QTY "
        f"  FROM ST_XTRANS "
        f"  WHERE TRIM(UPPER(COALESCE({x_fromdoc}, ''))) IN ('PQ', 'PH_PQ') "
        f"  GROUP BY {x_fromkey}, {x_fromdtl}"
        f") T ON T.FROMDOCKEY = D.{d_fk} AND T.FROMDTLKEY = D.{d_key} "
        f"WHERE D.{d_fk} = {header_alias}.{key} "
        f"AND {line_ok} "
        f"AND CAST(COALESCE(D.{d_qty}, 0) AS DOUBLE PRECISION) "
        f"    > CAST(COALESCE(T.TRANSFERRED_QTY, 0) AS DOUBLE PRECISION)"
        f")"
    )
    return f"({has_transfer} AND NOT {has_remaining})"


def sql_exclude_fully_transferred_pr(
    cur: Any,
    *,
    header_alias: str = "H",
    header_key_col: str = "DOCKEY",
) -> str:
    """SQL fragment excluding fully transferred PRs from active lists."""
    return f"NOT {sql_pr_fully_transferred_predicate(cur, header_alias=header_alias, header_key_col=header_key_col)}"


def remaining_transfer_qty_by_detail(
    detail_qty_by_id: dict[int, Decimal | float | int | str],
    transferred_qty_by_id: dict[int, Decimal | float | int | str],
) -> dict[int, Decimal]:
    """Pure remaining qty map (detailId → max(0, qty - transferred))."""
    out: dict[int, Decimal] = {}
    for detail_id, qty_raw in detail_qty_by_id.items():
        qty = _as_decimal(qty_raw, "0")
        transferred = _as_decimal(transferred_qty_by_id.get(detail_id, 0), "0")
        remaining = qty - transferred
        out[int(detail_id)] = remaining if remaining > 0 else Decimal("0")
    return out


def is_purchase_request_fully_transferred(
    *,
    detail_qty_by_id: dict[int, Decimal | float | int | str],
    transferred_qty_by_id: dict[int, Decimal | float | int | str],
    transferable_detail_ids: set[int] | None = None,
) -> bool:
    """
    Pure completion check for tests and in-process filtering.

    Requires at least one transferred quantity and zero remaining on every
    transferable detail. Empty detail maps are not fully transferred.
    """
    if not detail_qty_by_id:
        return False
    ids = set(detail_qty_by_id)
    if transferable_detail_ids is not None:
        ids = {i for i in ids if int(i) in transferable_detail_ids}
    if not ids:
        return False
    any_transferred = any(
        _as_decimal(transferred_qty_by_id.get(i, 0), "0") > 0 for i in ids
    )
    if not any_transferred:
        return False
    remaining = remaining_transfer_qty_by_detail(
        {i: detail_qty_by_id[i] for i in ids},
        transferred_qty_by_id,
    )
    return all(remaining.get(i, Decimal("0")) <= 0 for i in ids)


__all__ = [
    "is_purchase_request_fully_transferred",
    "remaining_transfer_qty_by_detail",
    "sql_exclude_fully_transferred_pr",
    "sql_pr_fully_transferred_predicate",
]
