"""Reusable data loaders for procurement stock card metrics."""
from __future__ import annotations

from datetime import date
from typing import Any


def _clean_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _parse_iso_date(value: Any) -> date | None:
    text = _clean_str(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _fetch_grouped_qty_map(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, dict[str, float]]:
    cur.execute(sql, params)
    rows = cur.fetchall() or []

    result: dict[str, dict[str, float]] = {}
    for row in rows:
        item_code = _clean_str(row[0] if len(row) > 0 else None)
        location_code = _clean_str(row[1] if len(row) > 1 else None)
        qty = _to_float(row[2] if len(row) > 2 else 0)

        if not item_code or not location_code:
            continue

        if item_code not in result:
            result[item_code] = {}
        result[item_code][location_code] = qty

    return result


def _fetch_grouped_qty_pair_map(
    cur: Any, sql: str, params: tuple[Any, ...] = ()
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    """Like _fetch_grouped_qty_map but row has two quantity columns (SQTY-priority stack, SUOM-priority stack)."""
    cur.execute(sql, params)
    rows = cur.fetchall() or []
    sqty_result: dict[str, dict[str, float]] = {}
    suom_result: dict[str, dict[str, float]] = {}
    for row in rows:
        item_code = _clean_str(row[0] if len(row) > 0 else None)
        location_code = _clean_str(row[1] if len(row) > 1 else None)
        q_sq = _to_float(row[2] if len(row) > 2 else 0)
        q_su = _to_float(row[3] if len(row) > 3 else 0)
        if not item_code or not location_code:
            continue
        if item_code not in sqty_result:
            sqty_result[item_code] = {}
        if item_code not in suom_result:
            suom_result[item_code] = {}
        sqty_result[item_code][location_code] = q_sq
        suom_result[item_code][location_code] = q_su
    return sqty_result, suom_result


def _get_table_columns(cur: Any, table_name: str) -> set[str]:
    cur.execute(
        """
        SELECT TRIM(RF.RDB$FIELD_NAME)
        FROM RDB$RELATION_FIELDS RF
        WHERE RF.RDB$RELATION_NAME = ?
        """,
        (table_name.upper(),),
    )
    return {str(row[0]).strip().upper() for row in (cur.fetchall() or []) if row and row[0]}


def _pick_existing(columns: set[str], *candidates: str) -> str:
    for name in candidates:
        if name.upper() in columns:
            return name.upper()
    return ""


# SQL Accounting often stores table-prefixed FROMDOCTYPE (e.g. SL_SO) while eProcurement uses SO.
_ST_XTRANS_FROM_SO_SQL = "TRIM(UPPER(COALESCE(X.FROMDOCTYPE, ''))) IN ('SO', 'SL_SO')"
_ST_XTRANS_FROM_PO_SQL = "TRIM(UPPER(COALESCE(X.FROMDOCTYPE, ''))) IN ('PO', 'PH_PO')"
_ST_XTRANS_FROM_JO_SQL = "TRIM(UPPER(COALESCE(X.FROMDOCTYPE, ''))) IN ('JO', 'PD_JO')"


def _st_xtrans_from_pq_sql(x_from_doctype_col: str) -> str:
    """Match PR/PQ moves whether stored as PQ or PH_PQ."""
    col = _clean_str(x_from_doctype_col).upper() or "FROMDOCTYPE"
    return f"TRIM(UPPER(COALESCE(X.{col}, ''))) IN ('PQ', 'PH_PQ')"


def _status_filter_tokens(statuses: list[str]) -> list[str]:
    status_map = {
        "DRAFT": ["DRAFT", "0"],
        "SUBMITTED": ["SUBMITTED", "1"],
        "APPROVED": ["APPROVED", "2"],
        "REJECTED": ["REJECTED", "3"],
        "CANCELLED": ["CANCELLED", "4"],
        "PENDING": ["PENDING"],
        "ACTIVE": ["ACTIVE"],
        "INACTIVE": ["INACTIVE"],
    }
    tokens: list[str] = []
    for status in statuses:
        key = _clean_str(status).upper()
        if not key:
            continue
        tokens.extend(status_map.get(key, [key]))
    # Preserve order while deduplicating
    unique: list[str] = []
    for token in tokens:
        if token not in unique:
            unique.append(token)
    return unique


def _fetch_pr_qty_map(
    cur: Any,
    included_statuses: list[str],
    from_date: date | None = None,
    to_date: date | None = None,
    *,
    d_line_qty_expr: str | None = None,
    xtrans_moved_qty_expr: str | None = None,
) -> dict[str, dict[str, float]]:
    header_cols = _get_table_columns(cur, "PH_PQ")
    detail_cols = _get_table_columns(cur, "PH_PQDTL")
    xtrans_cols = _get_table_columns(cur, "ST_XTRANS")

    header_key_col = _pick_existing(header_cols, "DOCKEY", "PQKEY", "ID")
    detail_fk_col = _pick_existing(detail_cols, "DOCKEY", "PQKEY", "REQUEST_ID", "HEADER_ID")
    detail_key_col = _pick_existing(detail_cols, "DTLKEY", "PQDTLKEY", "ID")
    status_col = _pick_existing(header_cols, "STATUS")
    udf_status_col = _pick_existing(header_cols, "UDF_STATUS")
    request_no_col = _pick_existing(header_cols, "DOCNO", "REQUESTNO", "PRNO", "PURCHASEREQUESTNO")
    docdate_col = _pick_existing(header_cols, "DOCDATE", "REQUESTDATE", "POSTDATE", "TAXDATE")
    item_col = _pick_existing(detail_cols, "ITEMCODE", "CODE")
    qty_col = _pick_existing(detail_cols, "QTY", "QUANTITY", "SQTY")
    d_line_qty = d_line_qty_expr or _doc_line_stock_qty_expr(detail_cols, "D")
    location_col = _pick_existing(detail_cols, "LOCATION", "LOC", "STOCKLOCATION", "STORELOCATION")

    x_fromdoctype_col = _pick_existing(xtrans_cols, "FROMDOCTYPE")
    x_fromdockey_col = _pick_existing(xtrans_cols, "FROMDOCKEY")
    x_fromdtlkey_col = _pick_existing(xtrans_cols, "FROMDTLKEY")
    x_qty_col = _pick_existing(xtrans_cols, "QTY")
    x_sqty_col = _pick_existing(xtrans_cols, "SQTY")

    if not header_key_col or not detail_fk_col or (not status_col and not udf_status_col) or not item_col or not qty_col:
        return {}

    tokens = _status_filter_tokens(included_statuses)
    if not tokens:
        return {}

    placeholders = ", ".join(["?"] * len(tokens))
    location_expr = f"COALESCE(NULLIF(TRIM(CAST(D.{location_col} AS VARCHAR(40))), ''), '')" if location_col else "''"

    status_checks: list[str] = []
    if status_col:
        status_checks.append(f"UPPER(TRIM(CAST(H.{status_col} AS VARCHAR(20)))) IN ({placeholders})")
    if udf_status_col:
        status_checks.append(f"UPPER(TRIM(CAST(H.{udf_status_col} AS VARCHAR(20)))) IN ({placeholders})")

    status_where = " OR ".join(status_checks) if status_checks else "1=0"
    extra_filters: list[str] = []
    params_list: list[Any] = list(tuple(tokens) * len(status_checks))

    # Only include requests created through this module naming convention.
    # This avoids legacy PH_PQ rows being treated as pending PR reservations.
    if request_no_col:
        extra_filters.append(f"UPPER(TRIM(CAST(H.{request_no_col} AS VARCHAR(60)))) LIKE 'PR-%'")
    if docdate_col and from_date:
        extra_filters.append(f"H.{docdate_col} >= ?")
        params_list.append(from_date)
    if docdate_col and to_date:
        extra_filters.append(f"H.{docdate_col} <= ?")
        params_list.append(to_date)

    full_where = f"({status_where})"
    if extra_filters:
        full_where += " AND " + " AND ".join(extra_filters)

    params = tuple(params_list)

    x_effective = xtrans_moved_qty_expr or _xtrans_moved_qty_expr(xtrans_cols, "X")
    can_compute_outstanding = all(
        [
            detail_key_col,
            x_fromdoctype_col,
            x_fromdockey_col,
            x_fromdtlkey_col,
        ]
    ) and (x_effective != "0")

    if can_compute_outstanding:
        x_qty_expr = x_effective
        cur.execute(
            f"""
            SELECT
                D.{item_col} AS ITEM_CODE,
                {location_expr} AS LOCATION_CODE,
                CAST(
                    SUM(
                        CASE
                            WHEN (({d_line_qty}) - COALESCE(T.TRANSFERRED_QTY, 0)) > 0
                                THEN (({d_line_qty}) - COALESCE(T.TRANSFERRED_QTY, 0))
                            ELSE 0
                        END
                    )
                AS DOUBLE PRECISION) AS TOTAL_QTY
            FROM PH_PQDTL D
            JOIN PH_PQ H
              ON H.{header_key_col} = D.{detail_fk_col}
            LEFT JOIN (
                SELECT X.{x_fromdockey_col} AS FROMDOCKEY,
                       X.{x_fromdtlkey_col} AS FROMDTLKEY,
                       CAST(SUM(CAST({x_qty_expr} AS DOUBLE PRECISION)) AS DOUBLE PRECISION) AS TRANSFERRED_QTY
                FROM ST_XTRANS X
                WHERE ({_st_xtrans_from_pq_sql(x_fromdoctype_col)})
                GROUP BY X.{x_fromdockey_col}, X.{x_fromdtlkey_col}
            ) T
              ON T.FROMDOCKEY = D.{detail_fk_col}
             AND T.FROMDTLKEY = D.{detail_key_col}
            WHERE {full_where}
            GROUP BY D.{item_col}, {location_expr}
            """,
            params,
        )
    else:
        d_sum = d_line_qty if d_line_qty != "0" else f"COALESCE(D.{qty_col}, 0)"
        cur.execute(
            f"""
            SELECT
                D.{item_col} AS ITEM_CODE,
                {location_expr} AS LOCATION_CODE,
                CAST(SUM(CAST({d_sum} AS DOUBLE PRECISION)) AS DOUBLE PRECISION) AS TOTAL_QTY
            FROM PH_PQDTL D
            JOIN PH_PQ H
              ON H.{header_key_col} = D.{detail_fk_col}
            WHERE {full_where}
            GROUP BY D.{item_col}, {location_expr}
            """,
            params,
        )

    rows = cur.fetchall() or []
    result: dict[str, dict[str, float]] = {}
    for row in rows:
        item_code = _clean_str(row[0] if len(row) > 0 else None)
        location_code = _clean_str(row[1] if len(row) > 1 else None)
        qty = _to_float(row[2] if len(row) > 2 else 0)
        if not item_code:
            continue
        if item_code not in result:
            result[item_code] = {}
        result[item_code][location_code] = qty

    return result


def _row_value(row: Any, index: int) -> Any:
    if row is None:
        return None
    try:
        return row[index]
    except Exception:
        return None


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _format_date(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return value.isoformat()
    except Exception:
        text = str(value).strip()
        return text or None


def _fetch_metric_detail_rows(cur: Any, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    rows = cur.fetchall() or []

    details: list[dict[str, Any]] = []
    for row in rows:
        total_qty = _to_float(_row_value(row, 4))
        moved_qty = _to_float(_row_value(row, 5))
        outstanding_qty = _to_float(_row_value(row, 6))
        details.append(
            {
                "docno": _stringify(_row_value(row, 0)),
                "docdate": _format_date(_row_value(row, 1)),
                "party": _stringify(_row_value(row, 2)),
                "remarks": _stringify(_row_value(row, 3)),
                "total_qty": total_qty,
                "moved_qty": moved_qty,
                "outstanding_qty": outstanding_qty,
            }
        )

    return details


def _fetch_metric_detail_net_pair_rows(cur: Any, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    """Document-line breakdown with parallel SQ and SUOM outstanding (net of ST_XTRANS)."""
    cur.execute(sql, params)
    rows = cur.fetchall() or []

    details: list[dict[str, Any]] = []
    for row in rows:
        details.append(
            {
                "docno": _stringify(_row_value(row, 0)),
                "docdate": _format_date(_row_value(row, 1)),
                "party": _stringify(_row_value(row, 2)),
                "remarks": _stringify(_row_value(row, 3)),
                "outstanding_sqty": _to_float(_row_value(row, 4)),
                "outstanding_suomqty": _to_float(_row_value(row, 5)),
            }
        )

    return details


def _sql_coalesce_chain_from_columns(
    table_alias: str,
    column_set: set[str],
    *preferred_order: str,
) -> str:
    """Build COALESCE(a.C1, a.C2, …, 0) using only columns that exist (case-insensitive names)."""
    upper = {c.upper() for c in column_set}
    parts: list[str] = []
    for name in preferred_order:
        u = name.upper()
        if u in upper:
            parts.append(f"{table_alias}.{u}")
    if not parts:
        return "0"
    if len(parts) == 1:
        return f"COALESCE({parts[0]}, 0)"
    return "COALESCE(" + ", ".join(parts) + ", 0)"


def _doc_line_sqty_priority_expr(detail_cols: set[str], alias: str = "D") -> str:
    """Primary SQTY column, then QTY; treat SQTY = 0 as unset (same idea as SUOM stack)."""
    upper = {c.upper() for c in detail_cols}
    if "SQTY" in upper and "QTY" in upper:
        return f"COALESCE(NULLIF({alias}.SQTY, 0), COALESCE({alias}.QTY, 0), 0)"
    if "SQTY" in upper:
        return f"COALESCE(NULLIF({alias}.SQTY, 0), 0)"
    if "QTY" in upper:
        return f"COALESCE({alias}.QTY, 0)"
    return "0"


def _xtrans_sqty_priority_expr(xtrans_cols: set[str], alias: str = "X") -> str:
    """
    Magnitude of transfer qty on ``ST_XTRANS`` (SQ stack).

    Values copied from ``ST_TR`` (or stock direction) can be negative; ``ABS`` ensures
    outstanding = line − sum(moved) subtracts a positive moved amount.
    """
    upper = {c.upper() for c in xtrans_cols}
    inner = "0"
    if "SQTY" in upper and "QTY" in upper:
        inner = f"COALESCE(NULLIF({alias}.SQTY, 0), COALESCE({alias}.QTY, 0), 0)"
    elif "SQTY" in upper:
        inner = f"COALESCE(NULLIF({alias}.SQTY, 0), 0)"
    elif "QTY" in upper:
        inner = f"COALESCE({alias}.QTY, 0)"
    if inner == "0":
        return "0"
    return f"ABS(CAST(({inner}) AS DOUBLE PRECISION))"


def _st_tr_sqty_bare_expr_for_aggregate(st_tr_cols: set[str]) -> str:
    """ST_TR on-hand using SQTY then QTY (bare column names for GROUP BY queries)."""
    upper = {c.upper() for c in st_tr_cols}
    if "SQTY" in upper and "QTY" in upper:
        return "COALESCE(NULLIF(SQTY, 0), COALESCE(QTY, 0), 0)"
    if "SQTY" in upper:
        return "COALESCE(NULLIF(SQTY, 0), 0)"
    if "QTY" in upper:
        return "COALESCE(QTY, 0)"
    return "0"


def _st_tr_suom_stack_expr(table_alias: str, st_tr_cols: set[str]) -> str:
    """
    ST_TR on-hand in the SUOM report stack.
    UDF_SUOMQTY is authoritative: NULL is 0, and 0 remains 0.
    """
    upper = {c.upper() for c in st_tr_cols}
    if "UDF_SUOMQTY" in upper:
        return f"COALESCE({table_alias}.UDF_SUOMQTY, 0)"
    return "0"


def _xtrans_moved_qty_expr(xtrans_cols: set[str], alias: str = "X") -> str:
    """
    Magnitude of ``ST_XTRANS.SUOMQTY`` for the SUOMQTY report stack (no SQTY/QTY fallback).

    ``SUOMQTY`` may be negative when aligned with signed ``ST_TR`` postings; ``ABS`` keeps
    the summed moved quantity positive for line − moved outstanding.
    """
    upper = {c.upper() for c in xtrans_cols}
    if "SUOMQTY" in upper:
        return f"ABS(CAST(COALESCE({alias}.SUOMQTY, 0) AS DOUBLE PRECISION))"
    return "0"


def _doc_line_stock_qty_expr(detail_cols: set[str], alias: str = "D") -> str:
    """Document detail quantity for the SUOMQTY stack: ``SUOMQTY`` only (no SQTY/QTY fallback)."""
    upper = {c.upper() for c in detail_cols}
    if "SUOMQTY" in upper:
        return f"COALESCE({alias}.SUOMQTY, 0)"
    return "0"


def _st_tr_line_qty_expr(st_tr_cols: set[str], alias: str = "S") -> str:
    """ST_TR on-hand SUOM stack: UDF_SUOMQTY only."""
    return _st_tr_suom_stack_expr(alias, st_tr_cols)


def _st_tr_qty_bare_expr_for_aggregate(st_tr_cols: set[str]) -> str:
    """ST_TR SUOM quantity with no table alias; UDF_SUOMQTY only."""
    upper = {c.upper() for c in st_tr_cols}
    if "UDF_SUOMQTY" in upper:
        return "COALESCE(UDF_SUOMQTY, 0)"
    return "0"


def _docdate_filter_sql(
    from_date: date | None,
    to_date: date | None,
) -> tuple[str, tuple[Any, ...]]:
    """AND-clause fragment for H.DOCDATE (matches procurement stock card date range)."""
    parts: list[str] = []
    params: list[Any] = []
    if from_date is not None:
        parts.append("H.DOCDATE >= ?")
        params.append(from_date)
    if to_date is not None:
        parts.append("H.DOCDATE <= ?")
        params.append(to_date)
    if not parts:
        return "", ()
    return " AND " + " AND ".join(parts), tuple(params)


def _outstanding_pair(total_sq: float, total_su: float, moved_sq: float, moved_su: float) -> tuple[float, float]:
    def _o(t: float, m: float) -> float:
        v = t - m
        return v if v > 0 else 0.0

    return _o(total_sq, moved_sq), _o(total_su, moved_su)


def _fetch_one_sum_pair(cur: Any, sql: str, params: tuple[Any, ...]) -> tuple[float, float]:
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row or len(row) < 2:
        return 0.0, 0.0
    return _to_float(row[0]), _to_float(row[1])


def _stock_card_aggregate_totals_for_item_location(
    cur: Any,
    item: str,
    location: str,
    from_date: date | None,
    to_date: date | None,
) -> dict[str, float]:
    """
    Component totals (SQ and SUOM stacks) for one item+location, matching
    :func:`fetch_procurement_stock_card_data` without running document-level
    per-line GROUP BYs. Used to avoid repeated full breakdowns for the same
    key (e.g. need_to_buy and qty summary rows).
    """
    item = _clean_str(item)
    location = _clean_str(location)
    date_filter, date_params = _docdate_filter_sql(from_date, to_date)

    _sodtl_cols = _get_table_columns(cur, "SL_SODTL")
    _podtl_cols = _get_table_columns(cur, "PH_PODTL")
    _jodtl_cols = _get_table_columns(cur, "PD_JODTL")
    _sttr_cols = _get_table_columns(cur, "ST_TR")
    _xtrans_cols = _get_table_columns(cur, "ST_XTRANS")

    so_sl_sq = _doc_line_sqty_priority_expr(_sodtl_cols, "SL_SODTL")
    so_sl_su = _doc_line_stock_qty_expr(_sodtl_cols, "SL_SODTL")
    so_d_sq = _doc_line_sqty_priority_expr(_sodtl_cols, "D")
    so_d_su = _doc_line_stock_qty_expr(_sodtl_cols, "D")
    _po_d_sq = _doc_line_sqty_priority_expr(_podtl_cols, "D")
    _po_d_su = _doc_line_stock_qty_expr(_podtl_cols, "D")
    _jo_d_sq = _doc_line_sqty_priority_expr(_jodtl_cols, "D")
    _jo_d_su = _doc_line_stock_qty_expr(_jodtl_cols, "D")
    _avail_sq = _st_tr_sqty_bare_expr_for_aggregate(_sttr_cols)
    _avail_su = _st_tr_qty_bare_expr_for_aggregate(_sttr_cols)
    _x_sq = _xtrans_sqty_priority_expr(_xtrans_cols, "X")
    _x_su = _xtrans_moved_qty_expr(_xtrans_cols, "X")

    il2 = (item, location)
    a_sq, a_su = _fetch_one_sum_pair(
        cur,
        f"""
        SELECT CAST(SUM(CAST(({_avail_sq}) AS DOUBLE PRECISION)) AS DOUBLE PRECISION),
               CAST(SUM(CAST(({_avail_su}) AS DOUBLE PRECISION)) AS DOUBLE PRECISION)
        FROM ST_TR
        WHERE ITEMCODE = ? AND LOCATION = ?
        """,
        il2,
    )

    so_t_sq, so_t_su = _fetch_one_sum_pair(
        cur,
        f"""
        SELECT CAST(SUM(CAST(({so_sl_sq}) AS DOUBLE PRECISION)) AS DOUBLE PRECISION),
               CAST(SUM(CAST(({so_sl_su}) AS DOUBLE PRECISION)) AS DOUBLE PRECISION)
        FROM SL_SODTL
        JOIN SL_SO H ON H.DOCKEY = SL_SODTL.DOCKEY
        WHERE SL_SODTL.ITEMCODE = ? AND SL_SODTL.LOCATION = ?{date_filter}
        """,
        il2 + date_params,
    )
    so_m_sq, so_m_su = _fetch_one_sum_pair(
        cur,
        f"""
        SELECT CAST(SUM(CAST(({_x_sq}) AS DOUBLE PRECISION)) AS DOUBLE PRECISION),
               CAST(SUM(CAST(({_x_su}) AS DOUBLE PRECISION)) AS DOUBLE PRECISION)
        FROM ST_XTRANS X
        JOIN SL_SODTL D ON D.DOCKEY = X.FROMDOCKEY AND D.DTLKEY = X.FROMDTLKEY
        JOIN SL_SO H ON H.DOCKEY = D.DOCKEY
        WHERE ({_ST_XTRANS_FROM_SO_SQL}) AND D.ITEMCODE = ? AND D.LOCATION = ?{date_filter}
        """,
        il2 + date_params,
    )
    so_o_sq, so_o_su = _outstanding_pair(so_t_sq, so_t_su, so_m_sq, so_m_su)

    po_t_sq, po_t_su = _fetch_one_sum_pair(
        cur,
        f"""
        SELECT CAST(SUM(CAST(({_po_d_sq}) AS DOUBLE PRECISION)) AS DOUBLE PRECISION),
               CAST(SUM(CAST(({_po_d_su}) AS DOUBLE PRECISION)) AS DOUBLE PRECISION)
        FROM PH_PODTL D
        JOIN PH_PO H ON H.DOCKEY = D.DOCKEY
        WHERE D.ITEMCODE = ? AND D.LOCATION = ?{date_filter}
        """,
        il2 + date_params,
    )
    po_m_sq, po_m_su = _fetch_one_sum_pair(
        cur,
        f"""
        SELECT CAST(SUM(CAST(({_x_sq}) AS DOUBLE PRECISION)) AS DOUBLE PRECISION),
               CAST(SUM(CAST(({_x_su}) AS DOUBLE PRECISION)) AS DOUBLE PRECISION)
        FROM ST_XTRANS X
        JOIN PH_PODTL D ON D.DOCKEY = X.FROMDOCKEY AND D.DTLKEY = X.FROMDTLKEY
        JOIN PH_PO H ON H.DOCKEY = D.DOCKEY
        WHERE ({_ST_XTRANS_FROM_PO_SQL}) AND D.ITEMCODE = ? AND D.LOCATION = ?{date_filter}
        """,
        il2 + date_params,
    )
    po_o_sq, po_o_su = _outstanding_pair(po_t_sq, po_t_su, po_m_sq, po_m_su)

    jo_t_sq, jo_t_su = _fetch_one_sum_pair(
        cur,
        f"""
        SELECT CAST(SUM(CAST(({_jo_d_sq}) AS DOUBLE PRECISION)) AS DOUBLE PRECISION),
               CAST(SUM(CAST(({_jo_d_su}) AS DOUBLE PRECISION)) AS DOUBLE PRECISION)
        FROM PD_JODTL D
        JOIN PD_JO H ON H.DOCKEY = D.DOCKEY
        WHERE D.ITEMCODE = ? AND D.LOCATION = ?{date_filter}
        """,
        il2 + date_params,
    )
    jo_m_sq, jo_m_su = _fetch_one_sum_pair(
        cur,
        f"""
        SELECT CAST(SUM(CAST(({_x_sq}) AS DOUBLE PRECISION)) AS DOUBLE PRECISION),
               CAST(SUM(CAST(({_x_su}) AS DOUBLE PRECISION)) AS DOUBLE PRECISION)
        FROM ST_XTRANS X
        JOIN PD_JODTL D ON D.DOCKEY = X.FROMDOCKEY AND D.DTLKEY = X.FROMDTLKEY
        JOIN PD_JO H ON H.DOCKEY = D.DOCKEY
        WHERE ({_ST_XTRANS_FROM_JO_SQL}) AND D.ITEMCODE = ? AND D.LOCATION = ?{date_filter}
        """,
        il2 + date_params,
    )
    jo_o_sq, jo_o_su = _outstanding_pair(jo_t_sq, jo_t_su, jo_m_sq, jo_m_su)

    return {
        "avail_sq": a_sq,
        "avail_su": a_su,
        "so_o_sq": so_o_sq,
        "so_o_su": so_o_su,
        "po_o_sq": po_o_sq,
        "po_o_su": po_o_su,
        "jo_o_sq": jo_o_sq,
        "jo_o_su": jo_o_su,
    }


def _uom_expressions_for_breakdown(cur: Any, use_suom: bool) -> dict[str, str]:
    """Line qty and ST_XTRANS moved qty for SO, PO, JO breakdowns (aligns with stock card report).

    When ``use_suom`` is true, both sides use ``SUOMQTY`` only (no SQTY/QTY fallback).
    """
    sodtl = _get_table_columns(cur, "SL_SODTL")
    podtl = _get_table_columns(cur, "PH_PODTL")
    jodtl = _get_table_columns(cur, "PD_JODTL")
    xtrans = _get_table_columns(cur, "ST_XTRANS")
    if use_suom:
        return {
            "so_d": _doc_line_stock_qty_expr(sodtl, "D"),
            "po_d": _doc_line_stock_qty_expr(podtl, "D"),
            "jo_d": _doc_line_stock_qty_expr(jodtl, "D"),
            "x": _xtrans_moved_qty_expr(xtrans, "X"),
        }
    return {
        "so_d": _sql_coalesce_chain_from_columns("D", sodtl, "SQTY", "QTY"),
        "po_d": _sql_coalesce_chain_from_columns("D", podtl, "SQTY", "QTY"),
        "jo_d": _sql_coalesce_chain_from_columns("D", jodtl, "SQTY", "QTY"),
        "x": _xtrans_sqty_priority_expr(xtrans, "X"),
    }


def _st_tr_qty_column_for_mode(cur: Any, use_suom: bool) -> str:
    st_cols = _get_table_columns(cur, "ST_TR")
    if use_suom:
        e = _st_tr_line_qty_expr(st_cols, "S")
        return e if e != "0" else "0"
    q = _pick_existing(st_cols, "QTY", "QUANTITY", "BALANCE", "BALQTY")
    if q:
        return f"COALESCE(S.{q}, 0)"
    return "0"


def _st_tr_line_sqty_expr_sql(st_cols: set[str], alias: str = "S") -> str:
    """On-hand SQ stack for one ``ST_TR`` row (SQTY then QTY); matches aggregate logic."""
    upper = {c.upper() for c in st_cols}
    if "SQTY" in upper and "QTY" in upper:
        return (
            f"COALESCE(NULLIF({alias}.SQTY, 0), COALESCE({alias}.QTY, 0), 0)"
        )
    if "SQTY" in upper:
        return f"COALESCE(NULLIF({alias}.SQTY, 0), 0)"
    if "QTY" in upper:
        return f"COALESCE({alias}.QTY, 0)"
    return "0"


def _fetch_pr_pending_lines_for_item(
    cur: Any,
    item_code: str,
    location_code: str,
    from_date: date | None,
    to_date: date | None,
) -> list[dict[str, Any]]:
    """Single summary row: same aggregate as the stock card pending PR (PH_PQ/PH_PQDTL vs ST_XTRANS)."""
    item = _clean_str(item_code)
    loc = _clean_str(location_code)
    pr_map = _fetch_pr_qty_map(
        cur,
        ["DRAFT", "SUBMITTED", "PENDING", "APPROVED", "ACTIVE"],
        from_date,
        to_date,
    )
    total = _to_float((pr_map.get(item) or {}).get(loc, 0))
    return [
        {
            "docno": "e-PR (aggregated)",
            "docdate": None,
            "party": "PH_PQ + PH_PQDTL",
            "remarks": "Reserved quantity on open/approved purchase requests (see View e-PR for document-level detail).",
            "total_qty": total,
            "moved_qty": 0.0,
            "outstanding_qty": total,
        }
    ]


def fetch_procurement_metric_breakdown(
    cur: Any,
    metric: str,
    item_code: str,
    location_code: str,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    qty_mode: str = "SQTY",
    batch_filter: str | None = None,
) -> dict[str, Any]:
    original_metric = _clean_str(metric).lower() or "qty"
    metric_key = original_metric
    if metric_key == "suom_qty":
        metric_key = "qty"
        qty_mode = "SUOMQTY"
    qty_upper = _clean_str(qty_mode).upper()
    use_suom = qty_upper == "SUOMQTY"

    def _breakdown_parallel_sq_su_note(from_doctype: str) -> str:
        suf = " Filtered by order date if a report cutoff is set."
        type_hint = {
            "SO": "FROMDOCTYPE SO",
            "PO": "FROMDOCTYPE PO",
            "JO": "FROMDOCTYPE JO",
        }.get(from_doctype, f"FROMDOCTYPE={from_doctype}")
        return (
            f"Parallel SQTY and SUOMQTY outstanding per line (document qty minus ST_XTRANS moves; {type_hint})."
            + suf
        )

    def _m_out(key: str) -> str:
        if original_metric == "suom_qty" and key == "qty":
            return "suom_qty"
        return key

    item = _clean_str(item_code)
    location = _clean_str(location_code)

    if not item or not location:
        raise ValueError("Item code and location are required")

    date_filter, date_params = _docdate_filter_sql(from_date, to_date)

    if metric_key == "so_qty":
        usq = _uom_expressions_for_breakdown(cur, False)
        usu = _uom_expressions_for_breakdown(cur, True)
        d_sq, x_sq = usq["so_d"], usq["x"]
        d_su, x_su = usu["so_d"], usu["x"]
        so_sql_both = f"""
            SELECT
                Q.DOCNO,
                Q.DOCDATE,
                Q.COMPANYNAME,
                Q.REMS,
                Q.OSQ,
                Q.OSU
            FROM (
                SELECT
                    H.DOCNO,
                    H.DOCDATE,
                    H.COMPANYNAME,
                    D.DESCRIPTION AS REMS,
                    CAST(
                        MAX(CAST(({d_sq}) AS DOUBLE PRECISION))
                        - COALESCE(SUM(CAST(({x_sq}) AS DOUBLE PRECISION)), 0)
                        AS DOUBLE PRECISION
                    ) AS OSQ,
                    CAST(
                        MAX(CAST(({d_su}) AS DOUBLE PRECISION))
                        - COALESCE(SUM(CAST(({x_su}) AS DOUBLE PRECISION)), 0)
                        AS DOUBLE PRECISION
                    ) AS OSU
                FROM SL_SODTL D
                JOIN SL_SO H
                  ON H.DOCKEY = D.DOCKEY
                LEFT JOIN ST_XTRANS X
                  ON ({_ST_XTRANS_FROM_SO_SQL})
                 AND X.FROMDOCKEY = D.DOCKEY
                 AND X.FROMDTLKEY = D.DTLKEY
                WHERE D.ITEMCODE = ?
                  AND D.LOCATION = ?
                {date_filter}
                GROUP BY H.DOCKEY, D.DTLKEY, H.DOCNO, H.DOCDATE, H.COMPANYNAME, D.DESCRIPTION
            ) Q
            WHERE Q.OSQ > 0 OR Q.OSU > 0
            ORDER BY Q.DOCDATE DESC, Q.DOCNO DESC
            """
        params_so_both = (item, location) + date_params
        rows_both = _fetch_metric_detail_net_pair_rows(cur, so_sql_both, params_so_both)
        sum_sq = sum(_to_float(r.get("outstanding_sqty")) for r in rows_both)
        sum_su = sum(_to_float(r.get("outstanding_suomqty")) for r in rows_both)
        return {
            "metric": _m_out("so_qty"),
            "title": "S.O Qty Breakdown",
            "item_code": item,
            "location": location,
            "breakdown_style": "doc_net_pair",
            "rows": rows_both,
            "summary": {
                "value": sum_sq,
                "value_su": sum_su,
                "note": _breakdown_parallel_sq_su_note("SO"),
            },
        }

    if metric_key == "po_qty":
        usq = _uom_expressions_for_breakdown(cur, False)
        usu = _uom_expressions_for_breakdown(cur, True)
        d_sq, x_sq = usq["po_d"], usq["x"]
        d_su, x_su = usu["po_d"], usu["x"]
        po_sql_both = f"""
            SELECT
                Q.DOCNO,
                Q.DOCDATE,
                Q.COMPANYNAME,
                Q.REMS,
                Q.OSQ,
                Q.OSU
            FROM (
                SELECT
                    H.DOCNO,
                    H.DOCDATE,
                    H.COMPANYNAME,
                    D.DESCRIPTION AS REMS,
                    CAST(
                        MAX(CAST(({d_sq}) AS DOUBLE PRECISION))
                        - COALESCE(SUM(CAST(({x_sq}) AS DOUBLE PRECISION)), 0)
                        AS DOUBLE PRECISION
                    ) AS OSQ,
                    CAST(
                        MAX(CAST(({d_su}) AS DOUBLE PRECISION))
                        - COALESCE(SUM(CAST(({x_su}) AS DOUBLE PRECISION)), 0)
                        AS DOUBLE PRECISION
                    ) AS OSU
                FROM PH_PODTL D
                JOIN PH_PO H
                  ON H.DOCKEY = D.DOCKEY
                LEFT JOIN ST_XTRANS X
                  ON ({_ST_XTRANS_FROM_PO_SQL})
                 AND X.FROMDOCKEY = D.DOCKEY
                 AND X.FROMDTLKEY = D.DTLKEY
                WHERE D.ITEMCODE = ?
                  AND D.LOCATION = ?
                {date_filter}
                GROUP BY H.DOCKEY, D.DTLKEY, H.DOCNO, H.DOCDATE, H.COMPANYNAME, D.DESCRIPTION
            ) Q
            WHERE Q.OSQ > 0 OR Q.OSU > 0
            ORDER BY Q.DOCDATE DESC, Q.DOCNO DESC
            """
        rows_both = _fetch_metric_detail_net_pair_rows(cur, po_sql_both, (item, location) + date_params)
        sum_sq = sum(_to_float(r.get("outstanding_sqty")) for r in rows_both)
        sum_su = sum(_to_float(r.get("outstanding_suomqty")) for r in rows_both)
        return {
            "metric": _m_out("po_qty"),
            "title": "P.O Qty Breakdown",
            "item_code": item,
            "location": location,
            "breakdown_style": "doc_net_pair",
            "rows": rows_both,
            "summary": {
                "value": sum_sq,
                "value_su": sum_su,
                "note": _breakdown_parallel_sq_su_note("PO"),
            },
        }

    if metric_key == "jo_qty":
        usq = _uom_expressions_for_breakdown(cur, False)
        usu = _uom_expressions_for_breakdown(cur, True)
        d_sq, x_sq = usq["jo_d"], usq["x"]
        d_su, x_su = usu["jo_d"], usu["x"]
        jo_sql_both = f"""
            SELECT
                Q.DOCNO,
                Q.DOCDATE,
                Q.JDESC,
                Q.DDESC,
                Q.OSQ,
                Q.OSU
            FROM (
                SELECT
                    H.DOCNO,
                    H.DOCDATE,
                    H.DESCRIPTION AS JDESC,
                    D.DESCRIPTION AS DDESC,
                    CAST(
                        MAX(CAST(({d_sq}) AS DOUBLE PRECISION))
                        - COALESCE(SUM(CAST(({x_sq}) AS DOUBLE PRECISION)), 0)
                        AS DOUBLE PRECISION
                    ) AS OSQ,
                    CAST(
                        MAX(CAST(({d_su}) AS DOUBLE PRECISION))
                        - COALESCE(SUM(CAST(({x_su}) AS DOUBLE PRECISION)), 0)
                        AS DOUBLE PRECISION
                    ) AS OSU
                FROM PD_JODTL D
                JOIN PD_JO H
                  ON H.DOCKEY = D.DOCKEY
                LEFT JOIN ST_XTRANS X
                  ON ({_ST_XTRANS_FROM_JO_SQL})
                 AND X.FROMDOCKEY = D.DOCKEY
                 AND X.FROMDTLKEY = D.DTLKEY
                WHERE D.ITEMCODE = ?
                  AND D.LOCATION = ?
                {date_filter}
                GROUP BY H.DOCKEY, D.DTLKEY, H.DOCNO, H.DOCDATE, H.DESCRIPTION, D.DESCRIPTION
            ) Q
            WHERE Q.OSQ > 0 OR Q.OSU > 0
            ORDER BY Q.DOCDATE DESC, Q.DOCNO DESC
            """
        rows_both_j = _fetch_metric_detail_net_pair_rows(cur, jo_sql_both, (item, location) + date_params)
        sum_sq = sum(_to_float(r.get("outstanding_sqty")) for r in rows_both_j)
        sum_su = sum(_to_float(r.get("outstanding_suomqty")) for r in rows_both_j)
        return {
            "metric": _m_out("jo_qty"),
            "title": "J.O Qty Breakdown",
            "item_code": item,
            "location": location,
            "breakdown_style": "doc_net_pair",
            "rows": rows_both_j,
            "summary": {
                "value": sum_sq,
                "value_su": sum_su,
                "note": _breakdown_parallel_sq_su_note("JO"),
            },
        }

    if metric_key == "avail_qty":
        st_cols = _get_table_columns(cur, "ST_TR")
        desc_col = _pick_existing(
            st_cols, "DESCRIPTION", "DESC1", "DESC2", "REMARK1", "REMARKS", "MEMO", "NARRATION"
        )
        qty_col = _pick_existing(st_cols, "QTY", "QUANTITY", "BALANCE", "BALQTY")
        batch_col = _pick_existing(st_cols, "BATCH", "BATCHNO", "LOT", "BATCHCODE")
        dtl_col = _pick_existing(st_cols, "DTLKEY", "RID", "LINE", "LINENO")
        sq_line = _st_tr_line_sqty_expr_sql(st_cols, "S")
        su_line = _st_tr_suom_stack_expr("S", st_cols)
        st_qty_expr = _st_tr_qty_column_for_mode(cur, use_suom)

        if st_qty_expr == "0" and not qty_col:
            details = [
                {
                    "batch": "—",
                    "description": "ST_TR has no QTY column in metadata; cannot list stock lines.",
                    "sqty": 0.0,
                    "suomqty": 0.0,
                }
            ]
            return {
                "metric": _m_out("avail_qty"),
                "title": "Avail.Qty Breakdown",
                "item_code": item,
                "location": location,
                "breakdown_style": "st_tr_qty_pair",
                "rows": details,
                "summary": {"value": 0.0, "note": "Missing QTY on ST_TR."},
            }

        batch_filter_sql = ""
        batch_params: tuple[Any, ...] = ()
        bf = _clean_str(batch_filter) if batch_filter is not None else ""
        if bf and batch_col:
            batch_filter_sql = (
                f" AND TRIM(COALESCE(CAST(S.{batch_col} AS VARCHAR(200)), '')) = ?"
            )
            batch_params = (bf,)

        if batch_col:
            batch_sel = f"TRIM(COALESCE(CAST(S.{batch_col} AS VARCHAR(120)), ''))"
        else:
            batch_sel = "CAST('' AS VARCHAR(120))"
        if desc_col:
            desc_sel = f"TRIM(COALESCE(CAST(S.{desc_col} AS VARCHAR(200)), ''))"
        else:
            desc_sel = "CAST('' AS VARCHAR(200))"

        order_parts: list[str] = []
        if batch_col:
            order_parts.append(f"S.{batch_col}")
        if dtl_col:
            order_parts.append(f"S.{dtl_col}")
        order_clause = ", ".join(order_parts) if order_parts else "1"

        cur.execute(
            f"""
            SELECT
                {batch_sel} AS C_BATCH,
                {desc_sel} AS C_DESC,
                CAST(({sq_line}) AS DOUBLE PRECISION) AS C_SQ,
                CAST(({su_line}) AS DOUBLE PRECISION) AS C_SU
            FROM ST_TR S
            WHERE S.ITEMCODE = ?
              AND S.LOCATION = ?
            {batch_filter_sql}
            ORDER BY {order_clause}
            """,
            (item, location) + batch_params,
        )
        raw_rows = cur.fetchall() or []
        details: list[dict[str, Any]] = []
        total_sq = 0.0
        total_su = 0.0
        for row in raw_rows:
            batch = _stringify(_row_value(row, 0)) if len(row) > 0 else ""
            des = _stringify(_row_value(row, 1)) if len(row) > 1 else ""
            qty_sq = _to_float(_row_value(row, 2) if len(row) > 2 else 0)
            qty_su = _to_float(_row_value(row, 3) if len(row) > 3 else 0)
            total_sq += qty_sq
            total_su += qty_su
            details.append(
                {
                    "batch": batch or "—",
                    "description": des or "—",
                    "sqty": qty_sq,
                    "suomqty": qty_su,
                }
            )
        if not details:
            details = [
                {
                    "batch": "—",
                    "description": "No ST_TR records for this item/location.",
                    "sqty": 0.0,
                    "suomqty": 0.0,
                }
            ]
        bf_note = f" Filter: batch = {bf}." if bf else ""
        summary_payload: dict[str, Any] = {
            "value": total_sq,
            "value_su": total_su,
            "note": (
                "One row per ST_TR line (SQTY & SUOMQTY); Σ SQTY and Σ SUOMQTY."
                + bf_note
            ),
        }
        return {
            "metric": _m_out("avail_qty"),
            "title": "Avail.Qty Breakdown",
            "item_code": item,
            "location": location,
            "breakdown_style": "st_tr_qty_pair",
            "rows": details,
            "summary": summary_payload,
        }

    if metric_key == "pending_pr":
        pr_rows = _fetch_pr_pending_lines_for_item(
            cur, item, location, from_date, to_date
        )
        total_p = sum(_to_float(r.get("outstanding_qty")) for r in pr_rows)
        return {
            "metric": "pending_pr",
            "title": "Pending e-PR lines",
            "item_code": item,
            "location": location,
            "rows": pr_rows,
            "summary": {
                "value": total_p,
                "note": "Remaining PR line quantity not yet moved via ST_XTRANS (FROMDOCTYPE=PQ).",
            },
        }

    if metric_key == "need_to_buy":
        agg = _stock_card_aggregate_totals_for_item_location(
            cur, item, location, from_date, to_date
        )
        pqdtl_cols_nb = _get_table_columns(cur, "PH_PQDTL")
        xtrans_cols_nb = _get_table_columns(cur, "ST_XTRANS")
        pr_map_sq = _fetch_pr_qty_map(
            cur,
            ["DRAFT", "SUBMITTED", "PENDING", "APPROVED", "ACTIVE"],
            from_date,
            to_date,
            d_line_qty_expr=_doc_line_sqty_priority_expr(pqdtl_cols_nb, "D"),
            xtrans_moved_qty_expr=_xtrans_sqty_priority_expr(xtrans_cols_nb, "X"),
        )
        pr_map_su = _fetch_pr_qty_map(
            cur,
            ["DRAFT", "SUBMITTED", "PENDING", "APPROVED", "ACTIVE"],
            from_date,
            to_date,
            d_line_qty_expr=_doc_line_stock_qty_expr(pqdtl_cols_nb, "D"),
            xtrans_moved_qty_expr=_xtrans_moved_qty_expr(xtrans_cols_nb, "X"),
        )
        pending_sq = _to_float((pr_map_sq.get(item) or {}).get(location, 0))
        pending_su = _to_float((pr_map_su.get(item) or {}).get(location, 0))
        avail_sq = agg["avail_sq"]
        avail_su = agg["avail_su"]
        so_sq, so_su = agg["so_o_sq"], agg["so_o_su"]
        po_sq, po_su = agg["po_o_sq"], agg["po_o_su"]
        jo_sq, jo_su = agg["jo_o_sq"], agg["jo_o_su"]
        procurement_balance_sq = avail_sq + po_sq - so_sq - jo_sq
        procurement_balance_su = avail_su + po_su - so_su - jo_su
        base_need_sq = max(0.0, -procurement_balance_sq)
        base_need_su = max(0.0, -procurement_balance_su)
        need_sq = max(0.0, base_need_sq - pending_sq)
        need_su = max(0.0, base_need_su - pending_su)
        return {
            "metric": "need_to_buy",
            "title": "Need to buy breakdown",
            "item_code": item,
            "location": location,
            "breakdown_style": "component_net_pair",
            "rows": [
                {
                    "docno": "On hand (Avail.)",
                    "remarks": "Physical on-hand from ST_TR; document cutoff does not change this.",
                    "outstanding_sqty": avail_sq,
                    "outstanding_suomqty": avail_su,
                },
                {
                    "docno": "P.O (incoming)",
                    "remarks": "Outstanding PO lines (ST_XTRANS net).",
                    "outstanding_sqty": po_sq,
                    "outstanding_suomqty": po_su,
                },
                {
                    "docno": "S.O (demand)",
                    "remarks": "Outstanding SO lines.",
                    "outstanding_sqty": -so_sq,
                    "outstanding_suomqty": -so_su,
                },
                {
                    "docno": "J.O (demand)",
                    "remarks": "Outstanding JO lines.",
                    "outstanding_sqty": -jo_sq,
                    "outstanding_suomqty": -jo_su,
                },
                {
                    "docno": "Open e-PR",
                    "remarks": "Reserved on approved/pending purchase requests (PH_PQ, ST_XTRANS balance).",
                    "outstanding_sqty": -pending_sq,
                    "outstanding_suomqty": -pending_su,
                },
            ],
            "summary": {
                "value": need_sq,
                "value_su": need_su,
                "note": "Need = max(0, (S.O + J.O − Avail − P.O)) minus open e-PR; parallel SQTY and SUOMQTY.",
            },
        }

    if metric_key == "qty":
        agg = _stock_card_aggregate_totals_for_item_location(
            cur, item, location, from_date, to_date
        )
        a_sq, a_su = agg["avail_sq"], agg["avail_su"]
        so_sq, so_su = agg["so_o_sq"], agg["so_o_su"]
        po_sq, po_su = agg["po_o_sq"], agg["po_o_su"]
        jo_sq, jo_su = agg["jo_o_sq"], agg["jo_o_su"]
        qty_sq = a_sq + po_sq - so_sq - jo_sq
        qty_su = a_su + po_su - so_su - jo_su
        return {
            "metric": _m_out("qty"),
            "title": "SUOMQTY / Avail. Qty bridge" if original_metric == "suom_qty" else "Qty Breakdown",
            "item_code": item,
            "location": location,
            "breakdown_style": "component_net_pair",
            "rows": [
                {
                    "docno": "Avail.Qty",
                    "remarks": "ST_TR (on-hand); cutoff filters documents only, not physical stock.",
                    "outstanding_sqty": a_sq,
                    "outstanding_suomqty": a_su,
                },
                {
                    "docno": "S.O Qty",
                    "remarks": "Outstanding sales orders (document minus ST_XTRANS from SO).",
                    "outstanding_sqty": -so_sq,
                    "outstanding_suomqty": -so_su,
                },
                {
                    "docno": "P.O Qty",
                    "remarks": "Outstanding purchase orders (deducted in the grid).",
                    "outstanding_sqty": po_sq,
                    "outstanding_suomqty": po_su,
                },
                {
                    "docno": "J.O Qty",
                    "remarks": "Outstanding job orders.",
                    "outstanding_sqty": -jo_sq,
                    "outstanding_suomqty": -jo_su,
                },
            ],
            "summary": {
                "value": qty_sq,
                "value_su": qty_su,
                "note": "Qty = Avail + P.O − S.O − J.O; parallel SQTY and SUOMQTY.",
            },
        }

    raise ValueError(f"Unsupported metric: {metric}")


def fetch_st_tr_udf_suomqty_summary(cur: Any) -> dict[str, Any]:
    """Totals ``ST_TR.UDF_SUOMQTY`` (same SUOM basis as stock-card on-hand SUOM stack)."""
    st_cols = _get_table_columns(cur, "ST_TR")
    upper = {c.upper() for c in st_cols}
    if "UDF_SUOMQTY" not in upper:
        return {
            "udf_column_present": False,
            "total": 0.0,
            "note": "ST_TR has no UDF_SUOMQTY column.",
        }
    cur.execute(
        """
        SELECT CAST(COALESCE(SUM(CAST(COALESCE(UDF_SUOMQTY, 0) AS DOUBLE PRECISION)), 0) AS DOUBLE PRECISION)
        FROM ST_TR
        """
    )
    row = cur.fetchone() or ()
    total = _to_float(row[0] if len(row) > 0 else 0)
    return {
        "udf_column_present": True,
        "total": total
    }


def fetch_procurement_stock_card_data(
    cur: Any,
    from_date: date | None = None,
    to_date: date | None = None,
    qty_mode: str = "SQTY",
) -> tuple[list[str], list[dict[str, Any]]]:
    """Return locations and stock-card rows for procurement overall report.

    Each row includes parallel **SQTY-priority** and **SUOM-priority** quantity stacks
    (``*_sqty_by_location`` / ``*_suom_by_location``) for on-hand, S.O, P.O, J.O, Avail,
    pending PR, and need-to-buy. Legacy flat keys (``so_qty_by_location``, etc.) mirror
    ``qty_mode``: ``SQTY`` → SQTY stack, ``SUOMQTY`` → SUOM stack (same as before for SUOM clients).

    When ``from_date`` / ``to_date`` are set, S.O / P.O / J.O (and open PR) aggregates use
    document dates; **quantity on hand** from ``ST_TR`` is not cleared by the cutoff.
    """
    normalized_from = from_date if isinstance(from_date, date) else _parse_iso_date(from_date)
    normalized_to = to_date if isinstance(to_date, date) else _parse_iso_date(to_date)
    primary_is_suom = _clean_str(qty_mode).upper() == "SUOMQTY"

    _sodtl_cols = _get_table_columns(cur, "SL_SODTL")
    _podtl_cols = _get_table_columns(cur, "PH_PODTL")
    _jodtl_cols = _get_table_columns(cur, "PD_JODTL")
    _sttr_cols = _get_table_columns(cur, "ST_TR")
    _xtrans_cols = _get_table_columns(cur, "ST_XTRANS")
    _pqdtl_cols = _get_table_columns(cur, "PH_PQDTL")

    _so_doc_sq = _doc_line_sqty_priority_expr(_sodtl_cols, "SL_SODTL")
    _so_doc_su = _doc_line_stock_qty_expr(_sodtl_cols, "SL_SODTL")
    _po_doc_sq = _doc_line_sqty_priority_expr(_podtl_cols, "D")
    _po_doc_su = _doc_line_stock_qty_expr(_podtl_cols, "D")
    _jo_doc_sq = _doc_line_sqty_priority_expr(_jodtl_cols, "D")
    _jo_doc_su = _doc_line_stock_qty_expr(_jodtl_cols, "D")
    _avail_sq = _st_tr_sqty_bare_expr_for_aggregate(_sttr_cols)
    _avail_su = _st_tr_qty_bare_expr_for_aggregate(_sttr_cols)
    _x_sq = _xtrans_sqty_priority_expr(_xtrans_cols, "X")
    _x_su = _xtrans_moved_qty_expr(_xtrans_cols, "X")

    cur.execute("SELECT CODE FROM ST_LOCATION ORDER BY CODE")
    location_rows = cur.fetchall() or []
    locations = []
    for row in location_rows:
        location_code = _clean_str(row[0] if row and len(row) > 0 else None)
        if location_code:
            locations.append(location_code)

    cur.execute("SELECT CODE FROM ST_ITEM ORDER BY CODE")
    item_rows = cur.fetchall() or []
    item_codes = []
    for row in item_rows:
        code = _clean_str(row[0] if row and len(row) > 0 else None)
        if code:
            item_codes.append(code)

    date_params = tuple(value for value in (normalized_from, normalized_to) if value is not None)

    avail_sq_map, avail_su_map = _fetch_grouped_qty_pair_map(
        cur,
        f"""
        SELECT ITEMCODE,
               LOCATION,
               CAST(SUM(CAST({_avail_sq} AS DOUBLE PRECISION)) AS DOUBLE PRECISION),
               CAST(SUM(CAST({_avail_su} AS DOUBLE PRECISION)) AS DOUBLE PRECISION)
        FROM ST_TR
        GROUP BY ITEMCODE, LOCATION
        """,
    )

    so_total_sq, so_total_su = _fetch_grouped_qty_pair_map(
        cur,
        f"""
        SELECT SL_SODTL.ITEMCODE,
               SL_SODTL.LOCATION,
               CAST(SUM(CAST({_so_doc_sq} AS DOUBLE PRECISION)) AS DOUBLE PRECISION),
               CAST(SUM(CAST({_so_doc_su} AS DOUBLE PRECISION)) AS DOUBLE PRECISION)
        FROM SL_SODTL
                JOIN SL_SO H
                    ON H.DOCKEY = SL_SODTL.DOCKEY
                WHERE 1 = 1
                """
        + ("\n          AND H.DOCDATE >= ?" if normalized_from else "")
        + ("\n          AND H.DOCDATE <= ?" if normalized_to else "")
        + """
        GROUP BY SL_SODTL.ITEMCODE, SL_SODTL.LOCATION
                """,
        date_params,
    )
    so_moved_sq, so_moved_su = _fetch_grouped_qty_pair_map(
        cur,
        f"""
        SELECT D.ITEMCODE,
               D.LOCATION,
               CAST(SUM(CAST({_x_sq} AS DOUBLE PRECISION)) AS DOUBLE PRECISION),
               CAST(SUM(CAST({_x_su} AS DOUBLE PRECISION)) AS DOUBLE PRECISION)
        FROM ST_XTRANS X
        JOIN SL_SODTL D
          ON D.DOCKEY = X.FROMDOCKEY
         AND D.DTLKEY = X.FROMDTLKEY
                JOIN SL_SO H
                    ON H.DOCKEY = D.DOCKEY
        WHERE ({_ST_XTRANS_FROM_SO_SQL})
                """
        + ("\n          AND H.DOCDATE >= ?" if normalized_from else "")
        + ("\n          AND H.DOCDATE <= ?" if normalized_to else "")
        + """
        GROUP BY D.ITEMCODE, D.LOCATION
                """,
        date_params,
    )

    po_total_sq, po_total_su = _fetch_grouped_qty_pair_map(
        cur,
        f"""
        SELECT D.ITEMCODE,
               D.LOCATION,
               CAST(SUM(CAST({_po_doc_sq} AS DOUBLE PRECISION)) AS DOUBLE PRECISION),
               CAST(SUM(CAST({_po_doc_su} AS DOUBLE PRECISION)) AS DOUBLE PRECISION)
        FROM PH_PODTL D
        JOIN PH_PO H
          ON H.DOCKEY = D.DOCKEY
                WHERE 1 = 1
                """
        + ("\n          AND H.DOCDATE >= ?" if normalized_from else "")
        + ("\n          AND H.DOCDATE <= ?" if normalized_to else "")
        + """
        GROUP BY D.ITEMCODE, D.LOCATION
                """,
        date_params,
    )
    po_moved_sq, po_moved_su = _fetch_grouped_qty_pair_map(
        cur,
        f"""
        SELECT D.ITEMCODE,
               D.LOCATION,
               CAST(SUM(CAST({_x_sq} AS DOUBLE PRECISION)) AS DOUBLE PRECISION),
               CAST(SUM(CAST({_x_su} AS DOUBLE PRECISION)) AS DOUBLE PRECISION)
        FROM ST_XTRANS X
        JOIN PH_PODTL D
          ON D.DOCKEY = X.FROMDOCKEY
         AND D.DTLKEY = X.FROMDTLKEY
        JOIN PH_PO H
          ON H.DOCKEY = D.DOCKEY
        WHERE ({_ST_XTRANS_FROM_PO_SQL})
                """
        + ("\n          AND H.DOCDATE >= ?" if normalized_from else "")
        + ("\n          AND H.DOCDATE <= ?" if normalized_to else "")
        + """
        GROUP BY D.ITEMCODE, D.LOCATION
                """,
        date_params,
    )

    jo_total_sq, jo_total_su = _fetch_grouped_qty_pair_map(
        cur,
        f"""
        SELECT D.ITEMCODE,
               D.LOCATION,
               CAST(SUM(CAST({_jo_doc_sq} AS DOUBLE PRECISION)) AS DOUBLE PRECISION),
               CAST(SUM(CAST({_jo_doc_su} AS DOUBLE PRECISION)) AS DOUBLE PRECISION)
        FROM PD_JODTL D
        JOIN PD_JO H
          ON H.DOCKEY = D.DOCKEY
                WHERE 1 = 1
                """
        + ("\n          AND H.DOCDATE >= ?" if normalized_from else "")
        + ("\n          AND H.DOCDATE <= ?" if normalized_to else "")
        + """
        GROUP BY D.ITEMCODE, D.LOCATION
                """,
        date_params,
    )
    jo_moved_sq, jo_moved_su = _fetch_grouped_qty_pair_map(
        cur,
        f"""
        SELECT D.ITEMCODE,
               D.LOCATION,
               CAST(SUM(CAST({_x_sq} AS DOUBLE PRECISION)) AS DOUBLE PRECISION),
               CAST(SUM(CAST({_x_su} AS DOUBLE PRECISION)) AS DOUBLE PRECISION)
        FROM ST_XTRANS X
        JOIN PD_JODTL D
          ON D.DOCKEY = X.FROMDOCKEY
         AND D.DTLKEY = X.FROMDTLKEY
        JOIN PD_JO H
          ON H.DOCKEY = D.DOCKEY
        WHERE ({_ST_XTRANS_FROM_JO_SQL})
                """
        + ("\n          AND H.DOCDATE >= ?" if normalized_from else "")
        + ("\n          AND H.DOCDATE <= ?" if normalized_to else "")
        + """
        GROUP BY D.ITEMCODE, D.LOCATION
                """,
        date_params,
    )

    pr_d_sq = _doc_line_sqty_priority_expr(_pqdtl_cols, "D")
    pr_d_su = _doc_line_stock_qty_expr(_pqdtl_cols, "D")
    pr_pending_sq_map = _fetch_pr_qty_map(
        cur,
        ["DRAFT", "SUBMITTED", "PENDING", "APPROVED", "ACTIVE"],
        normalized_from,
        normalized_to,
        d_line_qty_expr=pr_d_sq,
        xtrans_moved_qty_expr=_x_sq,
    )
    pr_pending_su_map = _fetch_pr_qty_map(
        cur,
        ["DRAFT", "SUBMITTED", "PENDING", "APPROVED", "ACTIVE"],
        normalized_from,
        normalized_to,
        d_line_qty_expr=pr_d_su,
        xtrans_moved_qty_expr=_x_su,
    )

    def _outstanding(total: float, moved: float) -> float:
        v = total - moved
        return v if v > 0 else 0.0

    data: list[dict[str, Any]] = []
    for code in item_codes:
        so_sq = {loc: 0.0 for loc in locations}
        so_su = {loc: 0.0 for loc in locations}
        po_sq = {loc: 0.0 for loc in locations}
        po_su = {loc: 0.0 for loc in locations}
        jo_sq = {loc: 0.0 for loc in locations}
        jo_su = {loc: 0.0 for loc in locations}
        avail_sq = {loc: 0.0 for loc in locations}
        avail_su = {loc: 0.0 for loc in locations}
        qty_sq = {loc: 0.0 for loc in locations}
        qty_su = {loc: 0.0 for loc in locations}
        pending_sq = {loc: 0.0 for loc in locations}
        pending_su = {loc: 0.0 for loc in locations}
        need_sq = {loc: 0.0 for loc in locations}
        need_su = {loc: 0.0 for loc in locations}

        ia_sq = avail_sq_map.get(code, {})
        ia_su = avail_su_map.get(code, {})
        ist_sq = so_total_sq.get(code, {})
        ist_su = so_total_su.get(code, {})
        ism_sq = so_moved_sq.get(code, {})
        ism_su = so_moved_su.get(code, {})
        ipt_sq = po_total_sq.get(code, {})
        ipt_su = po_total_su.get(code, {})
        ipm_sq = po_moved_sq.get(code, {})
        ipm_su = po_moved_su.get(code, {})
        ijt_sq = jo_total_sq.get(code, {})
        ijt_su = jo_total_su.get(code, {})
        ijm_sq = jo_moved_sq.get(code, {})
        ijm_su = jo_moved_su.get(code, {})
        ipr_sq = pr_pending_sq_map.get(code, {})
        ipr_su = pr_pending_su_map.get(code, {})

        for location_code in locations:
            so_o_sq = _outstanding(ist_sq.get(location_code, 0), ism_sq.get(location_code, 0))
            so_o_su = _outstanding(ist_su.get(location_code, 0), ism_su.get(location_code, 0))
            po_o_sq = _outstanding(ipt_sq.get(location_code, 0), ipm_sq.get(location_code, 0))
            po_o_su = _outstanding(ipt_su.get(location_code, 0), ipm_su.get(location_code, 0))
            jo_o_sq = _outstanding(ijt_sq.get(location_code, 0), ijm_sq.get(location_code, 0))
            jo_o_su = _outstanding(ijt_su.get(location_code, 0), ijm_su.get(location_code, 0))

            so_sq[location_code] = so_o_sq
            so_su[location_code] = so_o_su
            po_sq[location_code] = po_o_sq
            po_su[location_code] = po_o_su
            jo_sq[location_code] = jo_o_sq
            jo_su[location_code] = jo_o_su

            raw_a_sq = ia_sq.get(location_code, 0)
            raw_a_su = ia_su.get(location_code, 0)
            # Document cutoff filters S.O / P.O / J.O / PR in SQL; qty on hand stays physical ST_TR.
            avail_sq[location_code] = raw_a_sq
            avail_su[location_code] = raw_a_su

            qty_sq[location_code] = (
                avail_sq[location_code] + po_sq[location_code] - so_sq[location_code] - jo_sq[location_code]
            )
            qty_su[location_code] = (
                avail_su[location_code] + po_su[location_code] - so_su[location_code] - jo_su[location_code]
            )

            pending_sq[location_code] = max(0.0, ipr_sq.get(location_code, 0))
            pending_su[location_code] = max(0.0, ipr_su.get(location_code, 0))

            bal_sq = avail_sq[location_code] + po_sq[location_code] - so_sq[location_code] - jo_sq[location_code]
            bal_su = avail_su[location_code] + po_su[location_code] - so_su[location_code] - jo_su[location_code]
            need_sq[location_code] = max(0.0, max(0.0, -bal_sq) - pending_sq[location_code])
            need_su[location_code] = max(0.0, max(0.0, -bal_su) - pending_su[location_code])

        primary_so = so_su if primary_is_suom else so_sq
        primary_po = po_su if primary_is_suom else po_sq
        primary_jo = jo_su if primary_is_suom else jo_sq
        primary_avail = avail_su if primary_is_suom else avail_sq
        primary_qty = qty_su if primary_is_suom else qty_sq
        primary_pending = pending_su if primary_is_suom else pending_sq
        primary_need = need_su if primary_is_suom else need_sq

        data.append(
            {
                "code": code,
                "so_qty": sum(primary_so.values()),
                "so_qty_by_location": primary_so,
                "so_qty_sqty_by_location": so_sq,
                "so_qty_suom_by_location": so_su,
                "po_qty": sum(primary_po.values()),
                "po_qty_by_location": primary_po,
                "po_qty_sqty_by_location": po_sq,
                "po_qty_suom_by_location": po_su,
                "jo_qty": sum(primary_jo.values()),
                "jo_qty_by_location": primary_jo,
                "jo_qty_sqty_by_location": jo_sq,
                "jo_qty_suom_by_location": jo_su,
                "qty": sum(primary_qty.values()),
                "qty_by_location": primary_qty,
                "qty_sqty_by_location": qty_sq,
                "qty_suom_by_location": qty_su,
                "avail_qty": sum(primary_avail.values()),
                "avail_qty_by_location": primary_avail,
                "avail_qty_sqty_by_location": avail_sq,
                "avail_qty_suom_by_location": avail_su,
                "pending_pr": sum(primary_pending.values()),
                "pending_pr_by_location": primary_pending,
                "pending_pr_sqty_by_location": pending_sq,
                "pending_pr_suom_by_location": pending_su,
                "need_to_buy": sum(primary_need.values()),
                "need_to_buy_by_location": primary_need,
                "need_to_buy_sqty_by_location": need_sq,
                "need_to_buy_suom_by_location": need_su,
            }
        )

    return locations, data
