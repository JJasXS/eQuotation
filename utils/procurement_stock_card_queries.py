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

    can_compute_outstanding = all(
        [
            detail_key_col,
            x_fromdoctype_col,
            x_fromdockey_col,
            x_fromdtlkey_col,
            (x_qty_col or x_sqty_col),
        ]
    )

    if can_compute_outstanding:
        x_qty_expr = (
            f"COALESCE(X.{x_sqty_col}, X.{x_qty_col}, 0)"
            if x_sqty_col and x_qty_col
            else (f"COALESCE(X.{x_sqty_col}, 0)" if x_sqty_col else f"COALESCE(X.{x_qty_col}, 0)")
        )
        cur.execute(
            f"""
            SELECT
                D.{item_col} AS ITEM_CODE,
                {location_expr} AS LOCATION_CODE,
                CAST(
                    SUM(
                        CASE
                            WHEN (COALESCE(D.{qty_col}, 0) - COALESCE(T.TRANSFERRED_QTY, 0)) > 0
                                THEN (COALESCE(D.{qty_col}, 0) - COALESCE(T.TRANSFERRED_QTY, 0))
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
                WHERE X.{x_fromdoctype_col} = ?
                GROUP BY X.{x_fromdockey_col}, X.{x_fromdtlkey_col}
            ) T
              ON T.FROMDOCKEY = D.{detail_fk_col}
             AND T.FROMDTLKEY = D.{detail_key_col}
            WHERE {full_where}
            GROUP BY D.{item_col}, {location_expr}
            """,
            tuple(["PQ", *params]),
        )
    else:
        cur.execute(
            f"""
            SELECT
                D.{item_col} AS ITEM_CODE,
                {location_expr} AS LOCATION_CODE,
                CAST(SUM(COALESCE(D.{qty_col}, 0)) AS DOUBLE PRECISION) AS TOTAL_QTY
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


def fetch_procurement_metric_breakdown(
    cur: Any,
    metric: str,
    item_code: str,
    location_code: str,
) -> dict[str, Any]:
    metric_key = _clean_str(metric).lower()
    item = _clean_str(item_code)
    location = _clean_str(location_code)

    if not item or not location:
        raise ValueError("Item code and location are required")

    if metric_key == "so_qty":
        rows = _fetch_metric_detail_rows(
            cur,
            """
            SELECT
                H.DOCNO,
                H.DOCDATE,
                H.COMPANYNAME,
                D.DESCRIPTION,
                CAST(COALESCE(D.SQTY, D.QTY, 0) AS DOUBLE PRECISION) AS TOTAL_QTY,
                CAST(COALESCE(SUM(COALESCE(X.SQTY, X.QTY, 0)), 0) AS DOUBLE PRECISION) AS MOVED_QTY,
                CAST(
                    COALESCE(D.SQTY, D.QTY, 0)
                    - COALESCE(SUM(COALESCE(X.SQTY, X.QTY, 0)), 0)
                    AS DOUBLE PRECISION
                ) AS OUTSTANDING_QTY
            FROM SL_SODTL D
            JOIN SL_SO H
              ON H.DOCKEY = D.DOCKEY
            LEFT JOIN ST_XTRANS X
              ON X.FROMDOCTYPE = 'SO'
             AND X.FROMDOCKEY = D.DOCKEY
             AND X.FROMDTLKEY = D.DTLKEY
            WHERE D.ITEMCODE = ?
              AND D.LOCATION = ?
            GROUP BY H.DOCNO, H.DOCDATE, H.COMPANYNAME, D.DESCRIPTION, D.SQTY, D.QTY, H.DOCKEY, D.DTLKEY
            HAVING (
                COALESCE(D.SQTY, D.QTY, 0)
                - COALESCE(SUM(COALESCE(X.SQTY, X.QTY, 0)), 0)
            ) > 0
            ORDER BY H.DOCDATE DESC, H.DOCNO DESC
            """,
            (item, location),
        )
        return {
            "metric": metric_key,
            "title": "S.O Qty Breakdown",
            "item_code": item,
            "location": location,
            "rows": rows,
            "summary": {
                "value": sum(_to_float(row.get("outstanding_qty")) for row in rows),
                "note": "Outstanding sales order quantity = document SQTY minus transferred SQTY.",
            },
        }

    if metric_key == "po_qty":
        rows = _fetch_metric_detail_rows(
            cur,
            """
            SELECT
                H.DOCNO,
                H.DOCDATE,
                H.COMPANYNAME,
                D.DESCRIPTION,
                CAST(COALESCE(D.SQTY, D.QTY, 0) AS DOUBLE PRECISION) AS TOTAL_QTY,
                CAST(COALESCE(SUM(COALESCE(X.SQTY, X.QTY, 0)), 0) AS DOUBLE PRECISION) AS MOVED_QTY,
                CAST(
                    COALESCE(D.SQTY, D.QTY, 0)
                    - COALESCE(SUM(COALESCE(X.SQTY, X.QTY, 0)), 0)
                    AS DOUBLE PRECISION
                ) AS OUTSTANDING_QTY
            FROM PH_PODTL D
            JOIN PH_PO H
              ON H.DOCKEY = D.DOCKEY
            LEFT JOIN ST_XTRANS X
              ON X.FROMDOCTYPE = 'PO'
             AND X.FROMDOCKEY = D.DOCKEY
             AND X.FROMDTLKEY = D.DTLKEY
            WHERE D.ITEMCODE = ?
              AND D.LOCATION = ?
            GROUP BY H.DOCNO, H.DOCDATE, H.COMPANYNAME, D.DESCRIPTION, D.SQTY, D.QTY, H.DOCKEY, D.DTLKEY
            HAVING (
                COALESCE(D.SQTY, D.QTY, 0)
                - COALESCE(SUM(COALESCE(X.SQTY, X.QTY, 0)), 0)
            ) > 0
            ORDER BY H.DOCDATE DESC, H.DOCNO DESC
            """,
            (item, location),
        )
        return {
            "metric": metric_key,
            "title": "P.O Qty Breakdown",
            "item_code": item,
            "location": location,
            "rows": rows,
            "summary": {
                "value": sum(_to_float(row.get("outstanding_qty")) for row in rows),
                "note": "Outstanding purchase order quantity = document SQTY minus transferred SQTY.",
            },
        }

    if metric_key == "jo_qty":
        rows = _fetch_metric_detail_rows(
            cur,
            """
            SELECT
                H.DOCNO,
                H.DOCDATE,
                H.DESCRIPTION,
                D.DESCRIPTION,
                CAST(COALESCE(D.SQTY, D.QTY, 0) AS DOUBLE PRECISION) AS TOTAL_QTY,
                CAST(COALESCE(SUM(COALESCE(X.SQTY, X.QTY, 0)), 0) AS DOUBLE PRECISION) AS MOVED_QTY,
                CAST(
                    COALESCE(D.SQTY, D.QTY, 0)
                    - COALESCE(SUM(COALESCE(X.SQTY, X.QTY, 0)), 0)
                    AS DOUBLE PRECISION
                ) AS OUTSTANDING_QTY
            FROM PD_JODTL D
            JOIN PD_JO H
              ON H.DOCKEY = D.DOCKEY
            LEFT JOIN ST_XTRANS X
              ON X.FROMDOCTYPE = 'JO'
             AND X.FROMDOCKEY = D.DOCKEY
             AND X.FROMDTLKEY = D.DTLKEY
            WHERE D.ITEMCODE = ?
              AND D.LOCATION = ?
            GROUP BY H.DOCNO, H.DOCDATE, H.DESCRIPTION, D.DESCRIPTION, D.SQTY, D.QTY, H.DOCKEY, D.DTLKEY
            HAVING (
                COALESCE(D.SQTY, D.QTY, 0)
                - COALESCE(SUM(COALESCE(X.SQTY, X.QTY, 0)), 0)
            ) > 0
            ORDER BY H.DOCDATE DESC, H.DOCNO DESC
            """,
            (item, location),
        )
        return {
            "metric": metric_key,
            "title": "J.O Qty Breakdown",
            "item_code": item,
            "location": location,
            "rows": rows,
            "summary": {
                "value": sum(_to_float(row.get("outstanding_qty")) for row in rows),
                "note": "Outstanding job order quantity = document SQTY minus transferred SQTY.",
            },
        }

    if metric_key == "avail_qty":
        cur.execute(
            """
            SELECT DOCNO, DESCRIPTION, QTY
            FROM ST_TR
            WHERE ITEMCODE = ?
              AND LOCATION = ?
            ORDER BY DOCNO DESC
            """,
            (item, location),
        )
        rows = cur.fetchall() or []
        details = []
        total = 0.0
        for row in rows:
            qty = _to_float(_row_value(row, 2))
            total += qty
            details.append({
                "docno": _stringify(_row_value(row, 0)),
                "docdate": None,
                "party": None,
                "remarks": _stringify(_row_value(row, 1)),
                "total_qty": qty,
                "moved_qty": 0,
                "outstanding_qty": qty,
            })
        if not details:
            details.append({
                "docno": "ST_TR",
                "docdate": None,
                "party": None,
                "remarks": "No ST_TR records for this item/location.",
                "total_qty": 0,
                "moved_qty": 0,
                "outstanding_qty": 0,
            })
        return {
            "metric": metric_key,
            "title": "Avail.Qty Breakdown",
            "item_code": item,
            "location": location,
            "rows": details,
            "summary": {
                "value": total,
                "note": "Avail.Qty is the sum of QTY from all ST_TR records for this item/location.",
            },
        }

    if metric_key == "qty":
        so_data = fetch_procurement_metric_breakdown(cur, "so_qty", item, location)
        po_data = fetch_procurement_metric_breakdown(cur, "po_qty", item, location)
        jo_data = fetch_procurement_metric_breakdown(cur, "jo_qty", item, location)
        avail_data = fetch_procurement_metric_breakdown(cur, "avail_qty", item, location)

        avail_value = _to_float(avail_data["summary"].get("value"))
        so_value = _to_float(so_data["summary"].get("value"))
        po_value = _to_float(po_data["summary"].get("value"))
        jo_value = _to_float(jo_data["summary"].get("value"))
        qty_value = avail_value + so_value - po_value + jo_value

        return {
            "metric": metric_key,
            "title": "Qty Breakdown",
            "item_code": item,
            "location": location,
            "rows": [
                {
                    "docno": "Avail.Qty",
                    "docdate": None,
                    "party": None,
                    "remarks": "Current available quantity from ST_TR.",
                    "total_qty": avail_value,
                    "moved_qty": 0,
                    "outstanding_qty": avail_value,
                },
                {
                    "docno": "S.O Qty",
                    "docdate": None,
                    "party": None,
                    "remarks": "Outstanding sales orders added back into Qty.",
                    "total_qty": so_value,
                    "moved_qty": 0,
                    "outstanding_qty": so_value,
                },
                {
                    "docno": "P.O Qty",
                    "docdate": None,
                    "party": None,
                    "remarks": "Outstanding purchase orders deducted from Qty.",
                    "total_qty": po_value,
                    "moved_qty": 0,
                    "outstanding_qty": -po_value,
                },
                {
                    "docno": "J.O Qty",
                    "docdate": None,
                    "party": None,
                    "remarks": "Outstanding job orders added back into Qty.",
                    "total_qty": jo_value,
                    "moved_qty": 0,
                    "outstanding_qty": jo_value,
                },
            ],
            "summary": {
                "value": qty_value,
                "note": "Qty is derived in this report as Avail.Qty + S.O Qty - P.O Qty + J.O Qty.",
            },
        }

    raise ValueError(f"Unsupported metric: {metric}")


def fetch_procurement_stock_card_data(
    cur: Any,
    from_date: date | None = None,
    to_date: date | None = None,
    qty_mode: str = "SQTY",
) -> tuple[list[str], list[dict[str, Any]]]:
    """Return locations and stock-card rows for procurement overall report.

    qty_mode: 'SQTY' (default) uses QTY/SQTY fields; 'SUOMQTY' uses secondary
    UOM quantity fields (SUOMQTY) when available, falling back to QTY/SQTY.
    """
    normalized_from = from_date if isinstance(from_date, date) else _parse_iso_date(from_date)
    normalized_to = to_date if isinstance(to_date, date) else _parse_iso_date(to_date)
    use_suom = _clean_str(qty_mode).upper() == "SUOMQTY"

    # Detect SUOMQTY availability on each table when mode is SUOMQTY.
    if use_suom:
        _sodtl_cols  = _get_table_columns(cur, "SL_SODTL")
        _podtl_cols  = _get_table_columns(cur, "PH_PODTL")
        _jodtl_cols  = _get_table_columns(cur, "PD_JODTL")
        _sttr_cols   = _get_table_columns(cur, "ST_TR")
        _xtrans_cols = _get_table_columns(cur, "ST_XTRANS")

        def _doc_qty(alias: str, cols: set) -> str:
            if "SUOMQTY" in cols:
                return f"COALESCE({alias}.SUOMQTY, {alias}.QTY, 0)"
            return f"COALESCE({alias}.QTY, 0)"

        _so_doc_qty  = _doc_qty("SL_SODTL", _sodtl_cols)
        _po_doc_qty  = _doc_qty("D", _podtl_cols)
        _jo_doc_qty  = _doc_qty("D", _jodtl_cols)
        _avail_qty   = "COALESCE(SUOMQTY, QTY, 0)" if "SUOMQTY" in _sttr_cols else "QTY"

        _x_parts = []
        if "SUOMQTY" in _xtrans_cols:
            _x_parts.append("X.SUOMQTY")
        if "SQTY" in _xtrans_cols:
            _x_parts.append("X.SQTY")
        _x_parts.append("X.QTY")
        _x_parts.append("0")
        _xtrans_qty = "COALESCE(" + ", ".join(_x_parts) + ")"
    else:
        _so_doc_qty  = "QTY"
        _po_doc_qty  = "D.QTY"
        _jo_doc_qty  = "D.QTY"
        _avail_qty   = "QTY"
        _xtrans_qty  = "COALESCE(X.SQTY, X.QTY, 0)"

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

    avail_map = _fetch_grouped_qty_map(
        cur,
        f"""
        SELECT ITEMCODE,
               LOCATION,
               CAST(SUM(CAST({_avail_qty} AS DOUBLE PRECISION)) AS DOUBLE PRECISION) AS TOTAL_QTY
        FROM ST_TR
        GROUP BY ITEMCODE, LOCATION
        """,
    )

    so_total_map = _fetch_grouped_qty_map(
        cur,
        f"""
        SELECT ITEMCODE,
               LOCATION,
               CAST(SUM(CAST({_so_doc_qty} AS DOUBLE PRECISION)) AS DOUBLE PRECISION) AS TOTAL_SO_QTY
        FROM SL_SODTL
                JOIN SL_SO H
                    ON H.DOCKEY = SL_SODTL.DOCKEY
                WHERE 1 = 1
                """
                + ("\n          AND H.DOCDATE >= ?" if normalized_from else "")
                + ("\n          AND H.DOCDATE <= ?" if normalized_to else "")
                + """
        GROUP BY ITEMCODE, LOCATION
                """,
                tuple(value for value in (normalized_from, normalized_to) if value is not None),
    )
    so_moved_map = _fetch_grouped_qty_map(
        cur,
        f"""
        SELECT D.ITEMCODE,
               D.LOCATION,
               CAST(SUM(CAST({_xtrans_qty} AS DOUBLE PRECISION)) AS DOUBLE PRECISION) AS TOTAL_XTRANS_QTY
        FROM ST_XTRANS X
        JOIN SL_SODTL D
          ON D.DOCKEY = X.FROMDOCKEY
         AND D.DTLKEY = X.FROMDTLKEY
                JOIN SL_SO H
                    ON H.DOCKEY = D.DOCKEY
        WHERE X.FROMDOCTYPE = 'SO'
                """
                + ("\n          AND H.DOCDATE >= ?" if normalized_from else "")
                + ("\n          AND H.DOCDATE <= ?" if normalized_to else "")
                + """
        GROUP BY D.ITEMCODE, D.LOCATION
                """,
                tuple(value for value in (normalized_from, normalized_to) if value is not None),
    )

    po_total_map = _fetch_grouped_qty_map(
        cur,
        f"""
        SELECT D.ITEMCODE,
               D.LOCATION,
               CAST(SUM(CAST({_po_doc_qty} AS DOUBLE PRECISION)) AS DOUBLE PRECISION) AS TOTAL_PO_QTY
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
                tuple(value for value in (normalized_from, normalized_to) if value is not None),
    )
    po_moved_map = _fetch_grouped_qty_map(
        cur,
        f"""
        SELECT D.ITEMCODE,
               D.LOCATION,
               CAST(SUM(CAST({_xtrans_qty} AS DOUBLE PRECISION)) AS DOUBLE PRECISION) AS TOTAL_XTRANS_QTY
        FROM ST_XTRANS X
        JOIN PH_PODTL D
          ON D.DOCKEY = X.FROMDOCKEY
         AND D.DTLKEY = X.FROMDTLKEY
        JOIN PH_PO H
          ON H.DOCKEY = D.DOCKEY
        WHERE X.FROMDOCTYPE = 'PO'
                """
                + ("\n          AND H.DOCDATE >= ?" if normalized_from else "")
                + ("\n          AND H.DOCDATE <= ?" if normalized_to else "")
                + """
        GROUP BY D.ITEMCODE, D.LOCATION
                """,
                tuple(value for value in (normalized_from, normalized_to) if value is not None),
    )

    jo_total_map = _fetch_grouped_qty_map(
        cur,
        f"""
        SELECT D.ITEMCODE,
               D.LOCATION,
               CAST(SUM(CAST({_jo_doc_qty} AS DOUBLE PRECISION)) AS DOUBLE PRECISION) AS TOTAL_JO_QTY
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
                tuple(value for value in (normalized_from, normalized_to) if value is not None),
    )
    jo_moved_map = _fetch_grouped_qty_map(
        cur,
        f"""
        SELECT D.ITEMCODE,
               D.LOCATION,
               CAST(SUM(CAST({_xtrans_qty} AS DOUBLE PRECISION)) AS DOUBLE PRECISION) AS TOTAL_XTRANS_QTY
        FROM ST_XTRANS X
        JOIN PD_JODTL D
          ON D.DOCKEY = X.FROMDOCKEY
         AND D.DTLKEY = X.FROMDTLKEY
        JOIN PD_JO H
          ON H.DOCKEY = D.DOCKEY
        WHERE X.FROMDOCTYPE = 'JO'
                """
                + ("\n          AND H.DOCDATE >= ?" if normalized_from else "")
                + ("\n          AND H.DOCDATE <= ?" if normalized_to else "")
                + """
        GROUP BY D.ITEMCODE, D.LOCATION
                """,
                tuple(value for value in (normalized_from, normalized_to) if value is not None),
    )

    # Open PR reservation reduces need-to-buy until explicitly rejected/cancelled.
    # Include ACTIVE/APPROVED so approved PR balances still count as reserved demand.
    pr_pending_map = _fetch_pr_qty_map(
        cur,
        ["DRAFT", "SUBMITTED", "PENDING", "APPROVED", "ACTIVE"],
        normalized_from,
        normalized_to,
    )

    data: list[dict[str, Any]] = []
    for code in item_codes:
        so_qty_by_location = {location_code: 0 for location_code in locations}
        po_qty_by_location = {location_code: 0 for location_code in locations}
        jo_qty_by_location = {location_code: 0 for location_code in locations}
        qty_by_location = {location_code: 0 for location_code in locations}
        avail_qty_by_location = {location_code: 0 for location_code in locations}
        pending_pr_by_location = {location_code: 0 for location_code in locations}
        need_to_buy_by_location = {location_code: 0 for location_code in locations}

        item_avail = avail_map.get(code, {})
        item_so_total = so_total_map.get(code, {})
        item_so_moved = so_moved_map.get(code, {})
        item_po_total = po_total_map.get(code, {})
        item_po_moved = po_moved_map.get(code, {})
        item_jo_total = jo_total_map.get(code, {})
        item_jo_moved = jo_moved_map.get(code, {})
        item_pr_pending = pr_pending_map.get(code, {})

        for location_code in locations:
            so_outstanding = item_so_total.get(location_code, 0) - item_so_moved.get(location_code, 0)
            po_outstanding = item_po_total.get(location_code, 0) - item_po_moved.get(location_code, 0)
            jo_outstanding = item_jo_total.get(location_code, 0) - item_jo_moved.get(location_code, 0)

            so_qty_by_location[location_code] = so_outstanding if so_outstanding > 0 else 0
            po_qty_by_location[location_code] = po_outstanding if po_outstanding > 0 else 0
            jo_qty_by_location[location_code] = jo_outstanding if jo_outstanding > 0 else 0
            avail_qty_by_location[location_code] = item_avail.get(location_code, 0)
            qty_by_location[location_code] = (
                avail_qty_by_location[location_code]
                + so_qty_by_location[location_code]
                - po_qty_by_location[location_code]
                + jo_qty_by_location[location_code]
            )
            pending_pr = max(0.0, item_pr_pending.get(location_code, 0))
            # Procurement shortfall should treat PO as incoming supply and SO/JO as demand.
            procurement_balance = (
                avail_qty_by_location[location_code]
                + po_qty_by_location[location_code]
                - so_qty_by_location[location_code]
                - jo_qty_by_location[location_code]
            )
            base_need = max(0.0, -procurement_balance)
            pending_pr_by_location[location_code] = pending_pr
            # Only subtract pending PR (remaining not yet transferred)
            need_to_buy_by_location[location_code] = max(0.0, base_need - pending_pr)

        data.append(
            {
                "code": code,
                "so_qty": sum(so_qty_by_location.values()),
                "so_qty_by_location": so_qty_by_location,
                "po_qty": sum(po_qty_by_location.values()),
                "po_qty_by_location": po_qty_by_location,
                "jo_qty": sum(jo_qty_by_location.values()),
                "jo_qty_by_location": jo_qty_by_location,
                "qty": sum(qty_by_location.values()),
                "qty_by_location": qty_by_location,
                "avail_qty": sum(avail_qty_by_location.values()),
                "avail_qty_by_location": avail_qty_by_location,
                "pending_pr": sum(pending_pr_by_location.values()),
                "pending_pr_by_location": pending_pr_by_location,
                "need_to_buy": sum(need_to_buy_by_location.values()),
                "need_to_buy_by_location": need_to_buy_by_location,
            }
        )

    return locations, data
