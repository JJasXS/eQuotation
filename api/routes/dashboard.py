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
