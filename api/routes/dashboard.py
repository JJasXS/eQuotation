"""Dashboard metrics endpoints backed by Firebird queries."""
import os

import fdb
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException


load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

DB_PATH = os.getenv("DB_PATH")
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _connect_db():
    if not DB_PATH or not DB_HOST or not DB_USER or DB_PASSWORD is None:
        raise HTTPException(status_code=500, detail="Database credentials are not fully configured.")
    return fdb.connect(dsn=f"{DB_HOST}:{DB_PATH}", user=DB_USER, password=DB_PASSWORD, charset="UTF8")


def _sales_cycle_cte_sql() -> str:
    """Shared CTE for sales cycle calculation from QT to IV via ST_XTRANS flows."""
    return """
        WITH RECURSIVE
        xtrans_norm AS (
            SELECT
                xt.FROMDOCKEY,
                xt.TODOCKEY,
                CAST(UPPER(TRIM(COALESCE(xt.FROMDOCTYPE, ''))) AS VARCHAR(8)) AS FROMDOCTYPE,
                CAST(UPPER(TRIM(COALESCE(xt.TODOCTYPE, ''))) AS VARCHAR(8)) AS TODOCTYPE
            FROM ST_XTRANS xt
            WHERE xt.FROMDOCKEY IS NOT NULL
              AND xt.TODOCKEY IS NOT NULL
        ),
        invoice_base AS (
            SELECT DISTINCT
                iv.DOCKEY AS INVOICE_DOCKEY,
                CAST(iv.DOCDATE AS DATE) AS INVOICE_DOCDATE,
                TRIM(COALESCE(iv.DOCNO, '')) AS INVOICE_DOCNO
            FROM SL_IV iv
            WHERE iv.DOCKEY IS NOT NULL
              AND iv.DOCDATE IS NOT NULL
              AND (iv.CANCELLED IS NULL OR iv.CANCELLED = FALSE)
        ),
        flow AS (
            SELECT
                ib.INVOICE_DOCKEY,
                ib.INVOICE_DOCDATE,
                ib.INVOICE_DOCNO,
                xt.FROMDOCTYPE,
                xt.FROMDOCKEY,
                xt.TODOCTYPE,
                xt.TODOCKEY,
                1 AS DEPTH
            FROM invoice_base ib
            JOIN xtrans_norm xt
              ON xt.TODOCKEY = ib.INVOICE_DOCKEY
            WHERE xt.TODOCTYPE IN ('IV', 'SL_IV')
              AND xt.FROMDOCTYPE IN ('QT', 'SL_QT', 'SO', 'SL_SO', 'DO', 'SL_DO')

            UNION ALL

            SELECT
                f.INVOICE_DOCKEY,
                f.INVOICE_DOCDATE,
                f.INVOICE_DOCNO,
                xt.FROMDOCTYPE,
                xt.FROMDOCKEY,
                xt.TODOCTYPE,
                xt.TODOCKEY,
                f.DEPTH + 1
            FROM flow f
            JOIN xtrans_norm xt
              ON xt.TODOCKEY = f.FROMDOCKEY
             AND xt.TODOCTYPE = f.FROMDOCTYPE
            WHERE f.DEPTH < 8
              AND xt.FROMDOCTYPE IN ('QT', 'SL_QT', 'SO', 'SL_SO', 'DO', 'SL_DO')
              AND xt.TODOCTYPE IN ('QT', 'SL_QT', 'SO', 'SL_SO', 'DO', 'SL_DO', 'IV', 'SL_IV')
        ),
        quote_candidates AS (
            SELECT DISTINCT
                f.INVOICE_DOCKEY,
                f.INVOICE_DOCDATE,
                f.INVOICE_DOCNO,
                TRIM(COALESCE(qt.DOCNO, '')) AS QUOTATION_DOCNO,
                CAST(qt.DOCDATE AS DATE) AS QUOTATION_DOCDATE
            FROM flow f
            JOIN SL_QT qt
              ON qt.DOCKEY = f.FROMDOCKEY
            WHERE f.FROMDOCTYPE IN ('QT', 'SL_QT')
              AND qt.DOCDATE IS NOT NULL
              AND (qt.CANCELLED IS NULL OR qt.CANCELLED = FALSE)
              AND f.INVOICE_DOCDATE >= CAST(qt.DOCDATE AS DATE)
        ),
        per_invoice_min_dates AS (
            SELECT
                qc.INVOICE_DOCKEY,
                MIN(qc.QUOTATION_DOCDATE) AS QUOTATION_DOCDATE,
                MIN(qc.INVOICE_DOCDATE) AS INVOICE_DOCDATE
            FROM quote_candidates qc
            GROUP BY qc.INVOICE_DOCKEY
        ),
        per_invoice AS (
            SELECT
                p.INVOICE_DOCKEY,
                MIN(qc.INVOICE_DOCNO) AS INVOICE_DOCNO,
                p.QUOTATION_DOCDATE,
                p.INVOICE_DOCDATE,
                MIN(qc.QUOTATION_DOCNO) AS QUOTATION_DOCNO
            FROM per_invoice_min_dates p
            JOIN quote_candidates qc
              ON qc.INVOICE_DOCKEY = p.INVOICE_DOCKEY
             AND qc.QUOTATION_DOCDATE = p.QUOTATION_DOCDATE
            GROUP BY p.INVOICE_DOCKEY, p.QUOTATION_DOCDATE, p.INVOICE_DOCDATE
        ),
        metrics AS (
            SELECT
                pi.INVOICE_DOCKEY,
                pi.INVOICE_DOCNO,
                pi.QUOTATION_DOCNO,
                pi.QUOTATION_DOCDATE,
                pi.INVOICE_DOCDATE,
                CAST(DATEDIFF(DAY FROM pi.QUOTATION_DOCDATE TO pi.INVOICE_DOCDATE) AS INTEGER) AS SALES_CYCLE_DAYS
            FROM per_invoice pi
        )
    """


def get_sales_cycle_metrics() -> dict:
    """
    Compute sales cycle metrics from Quotation -> Invoice conversion.

    Uses ST_XTRANS to trace direct and multi-stage sales document flows:
    QT -> IV and QT -> SO -> DO -> IV.
    """
    sql = (
        _sales_cycle_cte_sql()
        + """
        SELECT
            CAST(COUNT(*) AS INTEGER) AS TOTAL_CONVERTED_INVOICES,
            CAST(COALESCE(SUM(m.SALES_CYCLE_DAYS), 0) AS INTEGER) AS TOTAL_SALES_CYCLE_DAYS,
            CAST(
                CASE
                    WHEN COUNT(*) = 0 THEN 0
                    ELSE CAST(SUM(m.SALES_CYCLE_DAYS) AS DOUBLE PRECISION) / CAST(COUNT(*) AS DOUBLE PRECISION)
                END
                AS DOUBLE PRECISION
            ) AS AVG_SALES_CYCLE_DAYS
        FROM metrics m
    """
    )

    con = None
    cur = None
    try:
        con = _connect_db()
        cur = con.cursor()
        cur.execute(sql)
        row = cur.fetchone()
        if not row:
            return {
                "total_converted_invoices": 0,
                "total_sales_cycle_days": 0,
                "avg_sales_cycle_days": 0,
            }

        total_converted_invoices = int(row[0] or 0)
        total_sales_cycle_days = int(row[1] or 0)
        avg_sales_cycle_days = float(row[2] or 0)

        return {
            "total_converted_invoices": total_converted_invoices,
            "total_sales_cycle_days": total_sales_cycle_days,
            "avg_sales_cycle_days": round(avg_sales_cycle_days, 2),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to compute sales cycle metrics: {str(exc)}")
    finally:
        if cur is not None:
            cur.close()
        if con is not None:
            con.close()


@router.get("/sales-cycle-metrics")
def sales_cycle_metrics():
    """Expose aggregated Sales Cycle metrics for dashboard consumption."""
    return get_sales_cycle_metrics()


@router.get("/sales-cycle-details")
def sales_cycle_details():
    """Expose detailed sales cycle rows for dashboard drill-down charts."""
    sql = (
        _sales_cycle_cte_sql()
        + """
        SELECT
            m.INVOICE_DOCKEY,
            m.INVOICE_DOCNO,
            m.QUOTATION_DOCNO,
            m.QUOTATION_DOCDATE,
            m.INVOICE_DOCDATE,
            m.SALES_CYCLE_DAYS,
            CAST(DATEDIFF(MINUTE FROM m.QUOTATION_DOCDATE TO m.INVOICE_DOCDATE) AS INTEGER) AS SALES_CYCLE_MINUTES,
            iv.COMPANYNAME
        FROM metrics m
        LEFT JOIN SL_IV iv ON iv.DOCKEY = m.INVOICE_DOCKEY
        ORDER BY m.SALES_CYCLE_DAYS DESC, m.INVOICE_DOCDATE ASC, m.INVOICE_DOCKEY ASC
    """
    )

    con = None
    cur = None
    try:
        con = _connect_db()
        cur = con.cursor()
        cur.execute(sql)
        rows = cur.fetchall() or []

        invoice_dockeys = [int(row[0]) for row in rows if row and row[0] is not None]
        invoice_items_by_dockey = {}

        if invoice_dockeys:
            in_clause = ", ".join(str(dockey) for dockey in sorted(set(invoice_dockeys)))
            cur.execute(
                f"""
                SELECT
                    d.DOCKEY,
                    TRIM(COALESCE(d.ITEMCODE, '')) AS ITEMCODE,
                    TRIM(COALESCE(d.DESCRIPTION, '')) AS DESCRIPTION,
                    CAST(COALESCE(d.QTY, 0) AS DOUBLE PRECISION) AS QTY,
                    TRIM(COALESCE(d.UOM, '')) AS UOM
                FROM SL_IVDTL d
                WHERE d.DOCKEY IN ({in_clause})
                ORDER BY d.DOCKEY, d.SEQ, d.DTLKEY
            """
            )

            for detail_dockey, itemcode, description, qty, uom in cur.fetchall() or []:
                key = int(detail_dockey)
                invoice_items_by_dockey.setdefault(key, []).append({
                    "itemcode": (itemcode or '').strip(),
                    "description": (description or '').strip(),
                    "qty": round(float(qty or 0), 4),
                    "uom": (uom or '').strip(),
                })

        items = []
        total_days = 0
        shortest_minutes = None
        longest_minutes = None

        for invoice_dockey, invoice_docno, quotation_docno, quotation_docdate, invoice_docdate, sales_cycle_days, sales_cycle_minutes, company_name in rows:
            cycle_days = int(sales_cycle_days or 0)
            cycle_minutes = int(sales_cycle_minutes or 0)
            total_days += cycle_days
            if shortest_minutes is None or cycle_minutes < shortest_minutes:
                shortest_minutes = cycle_minutes
            if longest_minutes is None or cycle_minutes > longest_minutes:
                longest_minutes = cycle_minutes

            # Compose display string: if < 1 day, show hours; else show days
            if cycle_days == 0:
                hours = max(1, int(round(cycle_minutes / 60.0)))
                display = f"{hours} hour(s)"
            else:
                display = f"{cycle_days} day(s)"

            items.append({
                "invoice_dockey": int(invoice_dockey),
                "invoice_docno": (invoice_docno or '').strip(),
                "quotation_docno": (quotation_docno or '').strip(),
                "quotation_docdate": quotation_docdate.isoformat() if quotation_docdate else None,
                "invoice_docdate": invoice_docdate.isoformat() if invoice_docdate else None,
                "sales_cycle_days": cycle_days,
                "sales_cycle_minutes": cycle_minutes,
                "sales_cycle_display": display,
                "company_name": (company_name or '').strip(),
                "invoice_items": invoice_items_by_dockey.get(int(invoice_dockey), []),
            })

        total_invoices = len(items)
        avg_days = (float(total_days) / float(total_invoices)) if total_invoices else 0.0

        # For summary, show shortest/longest as display string
        def display_from_minutes(minutes):
            if minutes is None:
                return "-"
            days = minutes // (60 * 24)
            if days == 0:
                hours = max(1, int(round(minutes / 60.0)))
                return f"{hours} hour(s)"
            else:
                return f"{days} day(s)"

        return {
            "total_converted_invoices": total_invoices,
            "total_sales_cycle_days": total_days,
            "avg_sales_cycle_days": round(avg_days, 2),
            "shortest_sales_cycle_display": display_from_minutes(shortest_minutes),
            "longest_sales_cycle_display": display_from_minutes(longest_minutes),
            "items": items,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load sales cycle details: {str(exc)}")
    finally:
        if cur is not None:
            cur.close()
        if con is not None:
            con.close()


def _qt_iv_conversion_sql() -> str:
    """Read-only QT->IV conversion report SQL using backward ST_XTRANS traversal.

    Business rules implemented:
    - Root traversal starts from invoice detail lines (SL_IVDTL).
    - Trace backward through ST_XTRANS until QT detail line is reached.
    - Ignore CN paths completely.
    - Only final invoice quantities count as completed sales.
    - Exclude cancelled quotation and invoice documents.
    """
    return """
        WITH RECURSIVE
        /* Normalize transfer links and keep only complete key-chain rows */
        xtrans_norm AS (
            SELECT
                CAST(UPPER(TRIM(COALESCE(xt.FROMDOCTYPE, ''))) AS VARCHAR(8)) AS FROMDOCTYPE,
                CAST(UPPER(TRIM(COALESCE(xt.TODOCTYPE, ''))) AS VARCHAR(8)) AS TODOCTYPE,
                xt.FROMDOCKEY,
                xt.TODOCKEY,
                xt.FROMDTLKEY,
                xt.TODTLKEY,
                CAST(COALESCE(xt.QTY, 0) AS DOUBLE PRECISION) AS LINK_QTY
            FROM ST_XTRANS xt
            WHERE xt.FROMDOCKEY IS NOT NULL
              AND xt.TODOCKEY IS NOT NULL
              AND xt.FROMDTLKEY IS NOT NULL
              AND xt.TODTLKEY IS NOT NULL
              AND xt.FROMDOCTYPE IS NOT NULL
              AND xt.TODOCTYPE IS NOT NULL
              AND CAST(UPPER(TRIM(COALESCE(xt.FROMDOCTYPE, ''))) AS VARCHAR(8)) NOT IN ('CN', 'SL_CN')
              AND CAST(UPPER(TRIM(COALESCE(xt.TODOCTYPE, ''))) AS VARCHAR(8)) NOT IN ('CN', 'SL_CN')
        ),

          /* Quotation roots: used for final output including non-invoiced lines */
          qt_root AS (
            SELECT
                qh.DOCKEY AS QT_DOCKEY,
                qd.DTLKEY AS QT_DTLKEY,
                TRIM(COALESCE(qh.DOCNO, '')) AS QT_DOCNO,
                CAST(qh.DOCDATE AS DATE) AS QT_DOCDATE,
                TRIM(COALESCE(qh.CODE, '')) AS CUSTOMER_CODE,
                TRIM(COALESCE(qh.COMPANYNAME, '')) AS CUSTOMER_NAME,
                TRIM(COALESCE(qd.ITEMCODE, '')) AS ITEMCODE,
                CAST(COALESCE(qd.QTY, 0) AS DOUBLE PRECISION) AS QT_QTY
            FROM SL_QT qh
            JOIN SL_QTDTL qd ON qd.DOCKEY = qh.DOCKEY
            WHERE qh.DOCKEY IS NOT NULL
              AND qd.DTLKEY IS NOT NULL
              AND qh.DOCDATE IS NOT NULL
              AND (qh.CANCELLED IS NULL OR qh.CANCELLED = FALSE)
        ),

        /* Invoice roots: start point for backward trace */
        iv_root AS (
            SELECT
                iv.DOCKEY AS IV_DOCKEY,
                ivd.DTLKEY AS IV_DTLKEY,
                CAST(COALESCE(ivd.QTY, 0) AS DOUBLE PRECISION) AS IV_LINE_QTY
            FROM SL_IV iv
            JOIN SL_IVDTL ivd ON ivd.DOCKEY = iv.DOCKEY
            WHERE iv.DOCKEY IS NOT NULL
              AND ivd.DTLKEY IS NOT NULL
              AND (iv.CANCELLED IS NULL OR iv.CANCELLED = FALSE)
        ),

        /* First backward hop from IV detail into previous stage */
        first_back_hop AS (
            SELECT
                i.IV_DOCKEY,
                i.IV_DTLKEY,
                i.IV_LINE_QTY,
                e.FROMDOCTYPE AS CURR_DOCTYPE,
                e.FROMDOCKEY AS CURR_DOCKEY,
                e.FROMDTLKEY AS CURR_DTLKEY,
                CAST(COALESCE(e.LINK_QTY, 0) AS DOUBLE PRECISION) AS PATH_QTY,
                1 AS DEPTH
            FROM iv_root i
            JOIN xtrans_norm e
              ON e.TODOCKEY = i.IV_DOCKEY
             AND e.TODTLKEY = i.IV_DTLKEY
             AND e.TODOCTYPE IN ('IV', 'SL_IV')
             AND e.FROMDOCTYPE IN ('QT', 'SL_QT', 'SO', 'SL_SO', 'DO', 'SL_DO')
        ),

        /*
          Backward traversal:
          previous FROM becomes next TODO until we reach QT.
        */
        backflow AS (
            SELECT
                b.IV_DOCKEY,
                b.IV_DTLKEY,
                b.IV_LINE_QTY,
                b.CURR_DOCTYPE,
                b.CURR_DOCKEY,
                b.CURR_DTLKEY,
                b.PATH_QTY,
                b.DEPTH
            FROM first_back_hop b

            UNION ALL

            SELECT
                c.IV_DOCKEY,
                c.IV_DTLKEY,
                c.IV_LINE_QTY,
                e.FROMDOCTYPE AS CURR_DOCTYPE,
                e.FROMDOCKEY AS CURR_DOCKEY,
                e.FROMDTLKEY AS CURR_DTLKEY,
                /* Keep conservative quantity along the path to avoid inflation */
                CAST(IIF(e.LINK_QTY < c.PATH_QTY, e.LINK_QTY, c.PATH_QTY) AS DOUBLE PRECISION) AS PATH_QTY,
                c.DEPTH + 1
            FROM backflow c
            JOIN xtrans_norm e
              ON e.TODOCTYPE = c.CURR_DOCTYPE
             AND e.TODOCKEY = c.CURR_DOCKEY
             AND e.TODTLKEY = c.CURR_DTLKEY
            WHERE c.DEPTH < 12
              AND c.CURR_DOCTYPE NOT IN ('QT', 'SL_QT')
              AND e.FROMDOCTYPE IN ('QT', 'SL_QT', 'SO', 'SL_SO', 'DO', 'SL_DO')
              AND e.TODOCTYPE IN ('SO', 'SL_SO', 'DO', 'SL_DO', 'IV', 'SL_IV')
        ),

        /* Resolve each IV detail line to the originating QT detail line(s) */
        iv_to_qt_raw AS (
            SELECT
                b.IV_DOCKEY,
                b.IV_DTLKEY,
                b.CURR_DOCKEY AS QT_DOCKEY,
                b.CURR_DTLKEY AS QT_DTLKEY,
                b.PATH_QTY AS IV_ALLOC_QTY
            FROM backflow b
            WHERE b.CURR_DOCTYPE IN ('QT', 'SL_QT')
        ),

        /*
          Dedupe protection for duplicated paths linking the same IV detail to
          the same QT detail.
        */
        iv_to_qt_dedup AS (
            SELECT
                r.IV_DOCKEY,
                r.IV_DTLKEY,
                r.QT_DOCKEY,
                r.QT_DTLKEY,
                MAX(r.IV_ALLOC_QTY) AS IV_ALLOC_QTY
            FROM iv_to_qt_raw r
            GROUP BY r.IV_DOCKEY, r.IV_DTLKEY, r.QT_DOCKEY, r.QT_DTLKEY
        ),

        /* Keep only non-cancelled IV headers */
        iv_valid AS (
            SELECT
                d.IV_DOCKEY,
                d.IV_DTLKEY,
                d.QT_DOCKEY,
                d.QT_DTLKEY,
                d.IV_ALLOC_QTY,
                CAST(iv.DOCDATE AS DATE) AS IV_DOCDATE,
                TRIM(COALESCE(iv.DOCNO, '')) AS IV_DOCNO
            FROM iv_to_qt_dedup d
            JOIN SL_IV iv ON iv.DOCKEY = d.IV_DOCKEY
            WHERE iv.DOCKEY IS NOT NULL
              AND (iv.CANCELLED IS NULL OR iv.CANCELLED = FALSE)
        ),

        iv_agg AS (
            SELECT
                v.QT_DOCKEY,
                v.QT_DTLKEY,
                CAST(COALESCE(SUM(v.IV_ALLOC_QTY), 0) AS DOUBLE PRECISION) AS IV_QTY,
                CAST(COUNT(DISTINCT v.IV_DOCKEY) AS INTEGER) AS INVOICE_COUNT,
                MAX(v.IV_DOCDATE) AS LATEST_IV_DATE
            FROM iv_valid v
            GROUP BY v.QT_DOCKEY, v.QT_DTLKEY
        )

        SELECT
            r.QT_DOCNO,
            r.QT_DOCDATE,
            r.CUSTOMER_CODE,
            r.CUSTOMER_NAME,
            r.ITEMCODE,
            r.QT_DOCKEY,
            r.QT_DTLKEY,
            CAST(r.QT_QTY AS DOUBLE PRECISION) AS QT_QTY,
            CAST(COALESCE(a.IV_QTY, 0) AS DOUBLE PRECISION) AS IV_QTY,
            CAST(
                CASE
                    WHEN COALESCE(r.QT_QTY, 0) = 0 THEN 0
                    ELSE (COALESCE(a.IV_QTY, 0) / r.QT_QTY) * 100
                END
                AS DOUBLE PRECISION
            ) AS CONVERSION_PCT,
            CAST(COALESCE(a.INVOICE_COUNT, 0) AS INTEGER) AS INVOICE_COUNT,
            a.LATEST_IV_DATE
        FROM qt_root r
        LEFT JOIN iv_agg a
          ON a.QT_DOCKEY = r.QT_DOCKEY
         AND a.QT_DTLKEY = r.QT_DTLKEY
        ORDER BY r.QT_DOCDATE DESC, r.QT_DOCNO, r.QT_DTLKEY
    """


@router.get("/qt-iv-conversion-report")
def qt_iv_conversion_report():
    """Expose QT->IV conversion report using direct Firebird SQL (read-only)."""
    sql = _qt_iv_conversion_sql()

    con = None
    cur = None
    try:
        con = _connect_db()
        cur = con.cursor()
        cur.execute(sql)
        rows = cur.fetchall() or []

        items = []
        total_qt_qty = 0.0
        total_iv_qty = 0.0
        not_invoiced_lines = 0
        partial_lines = 0
        full_or_over_lines = 0

        for (
            qt_docno,
            qt_docdate,
            customer_code,
            customer_name,
            itemcode,
            qt_dockey,
            qt_dtlkey,
            qt_qty,
            iv_qty,
            conversion_pct,
            invoice_count,
            latest_iv_date,
        ) in rows:
            qt_qty_val = float(qt_qty or 0)
            iv_qty_val = float(iv_qty or 0)
            pct_val = float(conversion_pct or 0)

            total_qt_qty += qt_qty_val
            total_iv_qty += iv_qty_val

            if iv_qty_val <= 0:
                not_invoiced_lines += 1
            elif iv_qty_val < qt_qty_val:
                partial_lines += 1
            else:
                full_or_over_lines += 1

            items.append({
                "qt_docno": (qt_docno or "").strip(),
                "qt_docdate": qt_docdate.isoformat() if qt_docdate else None,
                "customer_code": (customer_code or "").strip(),
                "customer_name": (customer_name or "").strip(),
                "itemcode": (itemcode or "").strip(),
                "qt_dockey": int(qt_dockey),
                "qt_dtlkey": int(qt_dtlkey),
                "qt_qty": round(qt_qty_val, 4),
                "iv_qty": round(iv_qty_val, 4),
                "conversion_pct": round(pct_val, 2),
                "invoice_count": int(invoice_count or 0),
                "latest_iv_date": latest_iv_date.isoformat() if latest_iv_date else None,
            })

        overall_pct = 0.0
        if total_qt_qty > 0:
            overall_pct = (total_iv_qty / total_qt_qty) * 100.0

        return {
            "total_qt_lines": len(items),
            "total_qt_qty": round(total_qt_qty, 4),
            "total_iv_qty": round(total_iv_qty, 4),
            "overall_conversion_pct": round(overall_pct, 2),
            "not_invoiced_lines": int(not_invoiced_lines),
            "partial_lines": int(partial_lines),
            "full_or_over_lines": int(full_or_over_lines),
            "items": items,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load QT->IV conversion report: {str(exc)}")
    finally:
        if cur is not None:
            cur.close()
        if con is not None:
            con.close()
