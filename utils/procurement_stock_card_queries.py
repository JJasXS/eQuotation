"""Reusable data loaders for procurement stock card metrics."""
from __future__ import annotations

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


def _fetch_grouped_qty_map(cur: Any, sql: str) -> dict[str, dict[str, float]]:
    cur.execute(sql)
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


def fetch_procurement_stock_card_data(cur: Any) -> tuple[list[str], list[dict[str, Any]]]:
    """Return locations and stock-card rows for procurement overall report."""
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
        """
        SELECT ITEMCODE,
               LOCATION,
               CAST(SUM(CAST(QTY AS DOUBLE PRECISION)) AS DOUBLE PRECISION) AS TOTAL_QTY
        FROM ST_TR
        GROUP BY ITEMCODE, LOCATION
        """,
    )

    so_total_map = _fetch_grouped_qty_map(
        cur,
        """
        SELECT ITEMCODE,
               LOCATION,
               CAST(SUM(CAST(QTY AS DOUBLE PRECISION)) AS DOUBLE PRECISION) AS TOTAL_SO_QTY
        FROM SL_SODTL
        GROUP BY ITEMCODE, LOCATION
        """,
    )
    so_moved_map = _fetch_grouped_qty_map(
        cur,
        """
        SELECT D.ITEMCODE,
               D.LOCATION,
               CAST(SUM(CAST(COALESCE(X.SQTY, X.QTY, 0) AS DOUBLE PRECISION)) AS DOUBLE PRECISION) AS TOTAL_XTRANS_QTY
        FROM ST_XTRANS X
        JOIN SL_SODTL D
          ON D.DOCKEY = X.FROMDOCKEY
         AND D.DTLKEY = X.FROMDTLKEY
        WHERE X.FROMDOCTYPE = 'SO'
        GROUP BY D.ITEMCODE, D.LOCATION
        """,
    )

    po_total_map = _fetch_grouped_qty_map(
        cur,
        """
        SELECT D.ITEMCODE,
               D.LOCATION,
               CAST(SUM(CAST(D.QTY AS DOUBLE PRECISION)) AS DOUBLE PRECISION) AS TOTAL_PO_QTY
        FROM PH_PODTL D
        JOIN PH_PO H
          ON H.DOCKEY = D.DOCKEY
        GROUP BY D.ITEMCODE, D.LOCATION
        """,
    )
    po_moved_map = _fetch_grouped_qty_map(
        cur,
        """
        SELECT D.ITEMCODE,
               D.LOCATION,
               CAST(SUM(CAST(COALESCE(X.SQTY, X.QTY, 0) AS DOUBLE PRECISION)) AS DOUBLE PRECISION) AS TOTAL_XTRANS_QTY
        FROM ST_XTRANS X
        JOIN PH_PODTL D
          ON D.DOCKEY = X.FROMDOCKEY
         AND D.DTLKEY = X.FROMDTLKEY
        JOIN PH_PO H
          ON H.DOCKEY = D.DOCKEY
        WHERE X.FROMDOCTYPE = 'PO'
        GROUP BY D.ITEMCODE, D.LOCATION
        """,
    )

    jo_total_map = _fetch_grouped_qty_map(
        cur,
        """
        SELECT D.ITEMCODE,
               D.LOCATION,
               CAST(SUM(CAST(D.QTY AS DOUBLE PRECISION)) AS DOUBLE PRECISION) AS TOTAL_JO_QTY
        FROM PD_JODTL D
        JOIN PD_JO H
          ON H.DOCKEY = D.DOCKEY
        GROUP BY D.ITEMCODE, D.LOCATION
        """,
    )
    jo_moved_map = _fetch_grouped_qty_map(
        cur,
        """
        SELECT D.ITEMCODE,
               D.LOCATION,
               CAST(SUM(CAST(COALESCE(X.SQTY, X.QTY, 0) AS DOUBLE PRECISION)) AS DOUBLE PRECISION) AS TOTAL_XTRANS_QTY
        FROM ST_XTRANS X
        JOIN PD_JODTL D
          ON D.DOCKEY = X.FROMDOCKEY
         AND D.DTLKEY = X.FROMDTLKEY
        JOIN PD_JO H
          ON H.DOCKEY = D.DOCKEY
        WHERE X.FROMDOCTYPE = 'JO'
        GROUP BY D.ITEMCODE, D.LOCATION
        """,
    )

    data: list[dict[str, Any]] = []
    for code in item_codes:
        so_qty_by_location = {location_code: 0 for location_code in locations}
        po_qty_by_location = {location_code: 0 for location_code in locations}
        jo_qty_by_location = {location_code: 0 for location_code in locations}
        qty_by_location = {location_code: 0 for location_code in locations}
        avail_qty_by_location = {location_code: 0 for location_code in locations}

        item_avail = avail_map.get(code, {})
        item_so_total = so_total_map.get(code, {})
        item_so_moved = so_moved_map.get(code, {})
        item_po_total = po_total_map.get(code, {})
        item_po_moved = po_moved_map.get(code, {})
        item_jo_total = jo_total_map.get(code, {})
        item_jo_moved = jo_moved_map.get(code, {})

        for location_code in locations:
            so_outstanding = item_so_total.get(location_code, 0) - item_so_moved.get(location_code, 0)
            po_outstanding = item_po_total.get(location_code, 0) - item_po_moved.get(location_code, 0)
            jo_outstanding = item_jo_total.get(location_code, 0) - item_jo_moved.get(location_code, 0)

            so_qty_by_location[location_code] = so_outstanding if so_outstanding > 0 else 0
            po_qty_by_location[location_code] = po_outstanding if po_outstanding > 0 else 0
            jo_qty_by_location[location_code] = jo_outstanding if jo_outstanding > 0 else 0
            avail_qty_by_location[location_code] = item_avail.get(location_code, 0)

        data.append(
            {
                "code": code,
                "so_qty": sum(so_qty_by_location.values()),
                "so_qty_by_location": so_qty_by_location,
                "po_qty": sum(po_qty_by_location.values()),
                "po_qty_by_location": po_qty_by_location,
                "jo_qty": sum(jo_qty_by_location.values()),
                "jo_qty_by_location": jo_qty_by_location,
                "qty": 0,
                "qty_by_location": qty_by_location,
                "avail_qty": sum(avail_qty_by_location.values()),
                "avail_qty_by_location": avail_qty_by_location,
            }
        )

    return locations, data
