"""Purchase request list/detail endpoints backed by local Firebird tables PH_PQ/PH_PQDTL."""
from __future__ import annotations

import os
from typing import Any

import fdb
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Query, Body

from api.routes.customers import verify_api_keys

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../.env'))
DB_PATH = os.getenv('DB_PATH')
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

router = APIRouter(tags=["Purchase Requests"])


def _connect_db() -> fdb.Connection:
    if not DB_PATH or not DB_HOST or not DB_USER:
        raise RuntimeError("DB connection environment is not fully configured")
    return fdb.connect(dsn=f"{DB_HOST}:{DB_PATH}", user=DB_USER, password=DB_PASSWORD, charset='UTF8')


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


def _to_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _to_number(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(str(value).replace(',', '').strip() or 0)
    except Exception:
        return 0.0


def _status_value(value: Any) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    try:
        return int(text)
    except Exception:
        return text


def _column_field_type(cur: Any, table_name: str, column_name: str) -> int | None:
    cur.execute(
        """
        SELECT F.RDB$FIELD_TYPE
        FROM RDB$RELATION_FIELDS RF
        JOIN RDB$FIELDS F ON RF.RDB$FIELD_SOURCE = F.RDB$FIELD_NAME
        WHERE RF.RDB$RELATION_NAME = ? AND RF.RDB$FIELD_NAME = ?
        """,
        (table_name.upper(), column_name.upper()),
    )
    row = cur.fetchone()
    if not row or row[0] is None:
        return None
    try:
        return int(row[0])
    except Exception:
        return None


def _encode_bool_for_column(cur: Any, table_name: str, column_name: str, value: bool) -> Any:
    field_type = _column_field_type(cur, table_name, column_name)
    # Firebird BOOLEAN field type is 23; numeric family uses 7/8/16/27.
    if field_type == 23:
        return bool(value)
    if field_type in {7, 8, 16, 27}:
        return 1 if value else 0
    return 'TRUE' if value else 'FALSE'


def _header_to_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "dockey": row.get("DOCKEY"),
        "docno": _to_text(row.get("DOCNO")),
        "docnoex": _to_text(row.get("DOCNOEX")),
        "docdate": _to_text(row.get("DOCDATE")),
        "postdate": _to_text(row.get("POSTDATE")),
        "taxdate": _to_text(row.get("TAXDATE")),
        "code": _to_text(row.get("CODE")) or "",
        "companyname": _to_text(row.get("COMPANYNAME")),
        "area": _to_text(row.get("AREA")) or "----",
        "agent": _to_text(row.get("AGENT")) or "----",
        "project": _to_text(row.get("PROJECT")) or "----",
        "currencycode": _to_text(row.get("CURRENCYCODE")) or "----",
        "currencyrate": _to_text(row.get("CURRENCYRATE")) or "1",
        "description": _to_text(row.get("DESCRIPTION")),
        "cancelled": bool(row.get("CANCELLED") or False),
        "status": _status_value(row.get("STATUS")),
        "docamt": str(_to_number(row.get("DOCAMT"))),
        "localdocamt": str(_to_number(row.get("DOCAMT"))),
        "businessunit": _to_text(row.get("BUSINESSUNIT")),
        "note": _to_text(row.get("NOTE")),
        "transferable": bool(row.get("TRANSFERABLE") if row.get("TRANSFERABLE") is not None else True),
        "lastmodified": row.get("LASTMODIFIED"),
        "udf_status": _to_text(row.get("UDF_STATUS")),
        "udf_pqapproved": row.get("UDF_PQAPPROVED"),
    }


def _fetch_detail_rows(cur: Any, dockey: int, detail_cols: set[str]) -> list[dict[str, Any]]:
    detail_key_col = _pick_existing(detail_cols, "DTLKEY", "PQDTLKEY", "ID")
    detail_fk_col = _pick_existing(detail_cols, "DOCKEY", "PQKEY", "REQUEST_ID", "HEADER_ID")
    seq_col = _pick_existing(detail_cols, "SEQ", "LINE_NO", "LINENO")
    item_code_col = _pick_existing(detail_cols, "ITEMCODE")
    location_col = _pick_existing(detail_cols, "LOCATION", "LOC", "STOCKLOCATION", "STORELOCATION")
    description_col = _pick_existing(detail_cols, "DESCRIPTION")
    description2_col = _pick_existing(detail_cols, "DESCRIPTION2", "ITEMNAME")
    description3_col = _pick_existing(detail_cols, "DESCRIPTION3")
    qty_col = _pick_existing(detail_cols, "QTY", "QUANTITY")
    unit_price_col = _pick_existing(detail_cols, "UNITPRICE")
    tax_amt_col = _pick_existing(detail_cols, "TAXAMT", "TAX")
    amount_col = _pick_existing(detail_cols, "AMOUNT", "TOTAL")
    approved_col = _pick_existing(detail_cols, "UDF_PQAPPROVED")

    if not detail_fk_col:
        return []

    select_cols = [
        f"D.{detail_key_col} AS DTLKEY" if detail_key_col else "NULL AS DTLKEY",
        f"D.{detail_fk_col} AS DOCKEY",
        f"D.{seq_col} AS SEQ" if seq_col else "NULL AS SEQ",
        f"D.{item_code_col} AS ITEMCODE" if item_code_col else "NULL AS ITEMCODE",
        f"D.{location_col} AS LOCATION" if location_col else "NULL AS LOCATION",
        f"D.{description_col} AS DESCRIPTION" if description_col else "NULL AS DESCRIPTION",
        f"D.{description2_col} AS DESCRIPTION2" if description2_col else "NULL AS DESCRIPTION2",
        f"D.{description3_col} AS DESCRIPTION3" if description3_col else "NULL AS DESCRIPTION3",
        f"D.{qty_col} AS QTY" if qty_col else "NULL AS QTY",
        f"D.{unit_price_col} AS UNITPRICE" if unit_price_col else "NULL AS UNITPRICE",
        f"D.{tax_amt_col} AS TAXAMT" if tax_amt_col else "NULL AS TAXAMT",
        f"D.{amount_col} AS AMOUNT" if amount_col else "NULL AS AMOUNT",
        f"D.{approved_col} AS UDF_PQAPPROVED" if approved_col else "NULL AS UDF_PQAPPROVED",
    ]

    order_col = seq_col or detail_key_col or detail_fk_col
    cur.execute(
        f"SELECT {', '.join(select_cols)} FROM PH_PQDTL D WHERE D.{detail_fk_col} = ? ORDER BY D.{order_col}",
        (dockey,),
    )

    rows = cur.fetchall() or []

    st_item_cols = _get_table_columns(cur, "ST_ITEM")
    st_desc_col = _pick_existing(st_item_cols, "DESCRIPTION")
    st_price_col = _pick_existing(st_item_cols, "UDF_STDPRICE")

    def _lookup_st_item(item_code: str) -> tuple[str | None, float | None]:
        if not item_code:
            return (None, None)
        if not st_desc_col and not st_price_col:
            return (None, None)

        select_parts = []
        if st_desc_col:
            select_parts.append(st_desc_col)
        if st_price_col:
            select_parts.append(st_price_col)
        if not select_parts:
            return (None, None)

        cur.execute(
            f"SELECT FIRST 1 {', '.join(select_parts)} FROM ST_ITEM WHERE CODE = ?",
            (item_code,),
        )
        row = cur.fetchone()
        if not row:
            return (None, None)

        idx = 0
        st_name = None
        st_price = None
        if st_desc_col:
            st_name = _to_text(row[idx])
            idx += 1
        if st_price_col:
            st_price = _to_number(row[idx])
        return (st_name, st_price)

    details: list[dict[str, Any]] = []
    for idx, r in enumerate(rows, start=1):
        item_code = _to_text(r[3])
        st_item_name, st_item_price = _lookup_st_item(item_code or "")
        detail_unit_price = _to_number(r[9])
        effective_unit_price = st_item_price if (st_item_price is not None and st_item_price > 0) else detail_unit_price

        details.append(
            {
                "dtlkey": r[0],
                "dockey": r[1],
                "seq": r[2] if r[2] is not None else idx,
                "itemcode": item_code,
                "location": _to_text(r[4]) or "----",
                "description": _to_text(r[5]),
                "description2": _to_text(r[6]) or st_item_name,
                "description3": _to_text(r[7]),
                "itemname": st_item_name or _to_text(r[6]) or _to_text(r[5]),
                "qty": str(_to_number(r[8])),
                "unitprice": str(effective_unit_price),
                "taxamt": str(_to_number(r[10])),
                "amount": str(_to_number(r[11])),
                "udf_pqapproved": r[12],
            }
        )
    return details


@router.get("/purchaserequest")
def list_purchase_requests(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    dockey: int | None = Query(None),
    id: int | None = Query(None),
    docno: str | None = Query(None),
    requestno: str | None = Query(None),
    _: None = Depends(verify_api_keys),
):
    """List purchase request headers with pagination and optional filtering."""
    con = None
    cur = None
    try:
        con = _connect_db()
        cur = con.cursor()
        header_cols = _get_table_columns(cur, "PH_PQ")

        if not header_cols:
            raise HTTPException(status_code=404, detail="PH_PQ table not found")

        key_col = _pick_existing(header_cols, "DOCKEY", "PQKEY", "ID")
        docno_col = _pick_existing(header_cols, "DOCNO", "REQUESTNO", "PRNO")
        docnoex_col = _pick_existing(header_cols, "DOCNOEX")
        docdate_col = _pick_existing(header_cols, "DOCDATE", "REQUESTDATE")
        postdate_col = _pick_existing(header_cols, "POSTDATE", "REQUIREDDATE")
        taxdate_col = _pick_existing(header_cols, "TAXDATE")
        code_col = _pick_existing(header_cols, "CODE", "REQUESTERID")
        company_col = _pick_existing(header_cols, "COMPANYNAME")
        area_col = _pick_existing(header_cols, "AREA")
        agent_col = _pick_existing(header_cols, "AGENT", "SUPPLIERID")
        project_col = _pick_existing(header_cols, "PROJECT")
        currency_col = _pick_existing(header_cols, "CURRENCYCODE", "CURRENCY")
        currency_rate_col = _pick_existing(header_cols, "CURRENCYRATE")
        desc_col = _pick_existing(header_cols, "DESCRIPTION", "JUSTIFICATION")
        cancelled_col = _pick_existing(header_cols, "CANCELLED")
        status_col = _pick_existing(header_cols, "STATUS")
        docamt_col = _pick_existing(header_cols, "DOCAMT", "TOTALAMT", "TOTAL_AMOUNT")
        businessunit_col = _pick_existing(header_cols, "BUSINESSUNIT", "DEPARTMENTID")
        note_col = _pick_existing(header_cols, "NOTE", "NOTES")
        transferable_col = _pick_existing(header_cols, "TRANSFERABLE")
        lastmodified_col = _pick_existing(header_cols, "LASTMODIFIED")
        udf_status_col = _pick_existing(header_cols, "UDF_STATUS")
        udf_approved_col = _pick_existing(header_cols, "UDF_PQAPPROVED")

        if not key_col:
            raise HTTPException(status_code=500, detail="PH_PQ key column not found")

        select_cols = [
            f"H.{key_col} AS DOCKEY",
            f"H.{docno_col} AS DOCNO" if docno_col else "NULL AS DOCNO",
            f"H.{docnoex_col} AS DOCNOEX" if docnoex_col else "NULL AS DOCNOEX",
            f"H.{docdate_col} AS DOCDATE" if docdate_col else "NULL AS DOCDATE",
            f"H.{postdate_col} AS POSTDATE" if postdate_col else "NULL AS POSTDATE",
            f"H.{taxdate_col} AS TAXDATE" if taxdate_col else "NULL AS TAXDATE",
            f"H.{code_col} AS CODE" if code_col else "NULL AS CODE",
            f"H.{company_col} AS COMPANYNAME" if company_col else "NULL AS COMPANYNAME",
            f"H.{area_col} AS AREA" if area_col else "NULL AS AREA",
            f"H.{agent_col} AS AGENT" if agent_col else "NULL AS AGENT",
            f"H.{project_col} AS PROJECT" if project_col else "NULL AS PROJECT",
            f"H.{currency_col} AS CURRENCYCODE" if currency_col else "NULL AS CURRENCYCODE",
            f"H.{currency_rate_col} AS CURRENCYRATE" if currency_rate_col else "NULL AS CURRENCYRATE",
            f"H.{desc_col} AS DESCRIPTION" if desc_col else "NULL AS DESCRIPTION",
            f"H.{cancelled_col} AS CANCELLED" if cancelled_col else "NULL AS CANCELLED",
            f"H.{status_col} AS STATUS" if status_col else "NULL AS STATUS",
            f"H.{docamt_col} AS DOCAMT" if docamt_col else "NULL AS DOCAMT",
            f"H.{businessunit_col} AS BUSINESSUNIT" if businessunit_col else "NULL AS BUSINESSUNIT",
            f"H.{note_col} AS NOTE" if note_col else "NULL AS NOTE",
            f"H.{transferable_col} AS TRANSFERABLE" if transferable_col else "NULL AS TRANSFERABLE",
            f"H.{lastmodified_col} AS LASTMODIFIED" if lastmodified_col else "NULL AS LASTMODIFIED",
            f"H.{udf_status_col} AS UDF_STATUS" if udf_status_col else "NULL AS UDF_STATUS",
            f"H.{udf_approved_col} AS UDF_PQAPPROVED" if udf_approved_col else "NULL AS UDF_PQAPPROVED",
        ]

        filters = []
        params: list[Any] = []
        query_key = dockey if dockey is not None else id
        if query_key is not None:
            filters.append(f"H.{key_col} = ?")
            params.append(int(query_key))

        doc_filter = (docno or requestno or '').strip()
        if doc_filter and docno_col:
            filters.append(f"H.{docno_col} = ?")
            params.append(doc_filter)

        where_sql = f" WHERE {' AND '.join(filters)}" if filters else ""

        if filters:
            cur.execute(f"SELECT COUNT(*) FROM PH_PQ H{where_sql}", tuple(params))
            total = int((cur.fetchone() or [0])[0] or 0)
            order_col = docdate_col or key_col
            cur.execute(
                f"SELECT {', '.join(select_cols)} FROM PH_PQ H{where_sql} ORDER BY H.{order_col} DESC",
                tuple(params),
            )
        else:
            cur.execute("SELECT COUNT(*) FROM PH_PQ")
            total = int((cur.fetchone() or [0])[0] or 0)
            order_col = docdate_col or key_col
            cur.execute(
                f"SELECT FIRST ? SKIP ? {', '.join(select_cols)} FROM PH_PQ H ORDER BY H.{order_col} DESC",
                (limit, offset),
            )

        rows = cur.fetchall() or []
        data = []
        for r in rows:
            row_map = {
                "DOCKEY": r[0],
                "DOCNO": r[1],
                "DOCNOEX": r[2],
                "DOCDATE": r[3],
                "POSTDATE": r[4],
                "TAXDATE": r[5],
                "CODE": r[6],
                "COMPANYNAME": r[7],
                "AREA": r[8],
                "AGENT": r[9],
                "PROJECT": r[10],
                "CURRENCYCODE": r[11],
                "CURRENCYRATE": r[12],
                "DESCRIPTION": r[13],
                "CANCELLED": r[14],
                "STATUS": r[15],
                "DOCAMT": r[16],
                "BUSINESSUNIT": r[17],
                "NOTE": r[18],
                "TRANSFERABLE": r[19],
                "LASTMODIFIED": r[20],
                "UDF_STATUS": r[21],
                "UDF_PQAPPROVED": r[22],
            }
            data.append(_header_to_payload(row_map))

        return {
            "pagination": {
                "offset": offset,
                "limit": limit,
                "count": len(data),
                "total": total,
            },
            "data": data,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to list purchase requests: {str(exc)}")
    finally:
        if cur is not None:
            cur.close()
        if con is not None:
            con.close()


@router.get("/purchaserequest/{request_ref}")
def get_purchase_request_detail(
    request_ref: str,
    _: None = Depends(verify_api_keys),
):
    """Get one purchase request with nested sdsdocdetail by dockey or docno."""
    con = None
    cur = None
    try:
        con = _connect_db()
        cur = con.cursor()
        header_cols = _get_table_columns(cur, "PH_PQ")
        detail_cols = _get_table_columns(cur, "PH_PQDTL")

        key_col = _pick_existing(header_cols, "DOCKEY", "PQKEY", "ID")
        docno_col = _pick_existing(header_cols, "DOCNO", "REQUESTNO", "PRNO")
        if not key_col:
            raise HTTPException(status_code=500, detail="PH_PQ key column not found")

        select_cols = [
            f"H.{key_col} AS DOCKEY",
            f"H.{docno_col} AS DOCNO" if docno_col else "NULL AS DOCNO",
            f"H.{_pick_existing(header_cols, 'DOCNOEX')} AS DOCNOEX" if _pick_existing(header_cols, 'DOCNOEX') else "NULL AS DOCNOEX",
            f"H.{_pick_existing(header_cols, 'DOCDATE', 'REQUESTDATE')} AS DOCDATE" if _pick_existing(header_cols, 'DOCDATE', 'REQUESTDATE') else "NULL AS DOCDATE",
            f"H.{_pick_existing(header_cols, 'POSTDATE', 'REQUIREDDATE')} AS POSTDATE" if _pick_existing(header_cols, 'POSTDATE', 'REQUIREDDATE') else "NULL AS POSTDATE",
            f"H.{_pick_existing(header_cols, 'TAXDATE')} AS TAXDATE" if _pick_existing(header_cols, 'TAXDATE') else "NULL AS TAXDATE",
            f"H.{_pick_existing(header_cols, 'CODE', 'REQUESTERID')} AS CODE" if _pick_existing(header_cols, 'CODE', 'REQUESTERID') else "NULL AS CODE",
            f"H.{_pick_existing(header_cols, 'COMPANYNAME')} AS COMPANYNAME" if _pick_existing(header_cols, 'COMPANYNAME') else "NULL AS COMPANYNAME",
            f"H.{_pick_existing(header_cols, 'AREA')} AS AREA" if _pick_existing(header_cols, 'AREA') else "NULL AS AREA",
            f"H.{_pick_existing(header_cols, 'AGENT', 'SUPPLIERID')} AS AGENT" if _pick_existing(header_cols, 'AGENT', 'SUPPLIERID') else "NULL AS AGENT",
            f"H.{_pick_existing(header_cols, 'PROJECT')} AS PROJECT" if _pick_existing(header_cols, 'PROJECT') else "NULL AS PROJECT",
            f"H.{_pick_existing(header_cols, 'CURRENCYCODE', 'CURRENCY')} AS CURRENCYCODE" if _pick_existing(header_cols, 'CURRENCYCODE', 'CURRENCY') else "NULL AS CURRENCYCODE",
            f"H.{_pick_existing(header_cols, 'CURRENCYRATE')} AS CURRENCYRATE" if _pick_existing(header_cols, 'CURRENCYRATE') else "NULL AS CURRENCYRATE",
            f"H.{_pick_existing(header_cols, 'DESCRIPTION', 'JUSTIFICATION')} AS DESCRIPTION" if _pick_existing(header_cols, 'DESCRIPTION', 'JUSTIFICATION') else "NULL AS DESCRIPTION",
            f"H.{_pick_existing(header_cols, 'CANCELLED')} AS CANCELLED" if _pick_existing(header_cols, 'CANCELLED') else "NULL AS CANCELLED",
            f"H.{_pick_existing(header_cols, 'STATUS')} AS STATUS" if _pick_existing(header_cols, 'STATUS') else "NULL AS STATUS",
            f"H.{_pick_existing(header_cols, 'DOCAMT', 'TOTALAMT', 'TOTAL_AMOUNT')} AS DOCAMT" if _pick_existing(header_cols, 'DOCAMT', 'TOTALAMT', 'TOTAL_AMOUNT') else "NULL AS DOCAMT",
            f"H.{_pick_existing(header_cols, 'BUSINESSUNIT', 'DEPARTMENTID')} AS BUSINESSUNIT" if _pick_existing(header_cols, 'BUSINESSUNIT', 'DEPARTMENTID') else "NULL AS BUSINESSUNIT",
            f"H.{_pick_existing(header_cols, 'NOTE', 'NOTES')} AS NOTE" if _pick_existing(header_cols, 'NOTE', 'NOTES') else "NULL AS NOTE",
            f"H.{_pick_existing(header_cols, 'TRANSFERABLE')} AS TRANSFERABLE" if _pick_existing(header_cols, 'TRANSFERABLE') else "NULL AS TRANSFERABLE",
            f"H.{_pick_existing(header_cols, 'LASTMODIFIED')} AS LASTMODIFIED" if _pick_existing(header_cols, 'LASTMODIFIED') else "NULL AS LASTMODIFIED",
            f"H.{_pick_existing(header_cols, 'UDF_STATUS')} AS UDF_STATUS" if _pick_existing(header_cols, 'UDF_STATUS') else "NULL AS UDF_STATUS",
            f"H.{_pick_existing(header_cols, 'UDF_PQAPPROVED')} AS UDF_PQAPPROVED" if _pick_existing(header_cols, 'UDF_PQAPPROVED') else "NULL AS UDF_PQAPPROVED",
        ]

        sql = f"SELECT FIRST 1 {', '.join(select_cols)} FROM PH_PQ H WHERE "
        params: tuple[Any, ...]
        if request_ref.isdigit():
            sql += f"H.{key_col} = ?"
            params = (int(request_ref),)
        elif docno_col:
            sql += f"H.{docno_col} = ?"
            params = (request_ref.strip(),)
        else:
            raise HTTPException(status_code=404, detail="Purchase request not found")

        cur.execute(sql, params)
        r = cur.fetchone()
        if not r:
            return {"data": []}

        row_map = {
            "DOCKEY": r[0],
            "DOCNO": r[1],
            "DOCNOEX": r[2],
            "DOCDATE": r[3],
            "POSTDATE": r[4],
            "TAXDATE": r[5],
            "CODE": r[6],
            "COMPANYNAME": r[7],
            "AREA": r[8],
            "AGENT": r[9],
            "PROJECT": r[10],
            "CURRENCYCODE": r[11],
            "CURRENCYRATE": r[12],
            "DESCRIPTION": r[13],
            "CANCELLED": r[14],
            "STATUS": r[15],
            "DOCAMT": r[16],
            "BUSINESSUNIT": r[17],
            "NOTE": r[18],
            "TRANSFERABLE": r[19],
            "LASTMODIFIED": r[20],
            "UDF_STATUS": r[21],
            "UDF_PQAPPROVED": r[22],
        }

        payload = _header_to_payload(row_map)
        payload["sdsdocdetail"] = _fetch_detail_rows(cur, int(payload["dockey"]), detail_cols)

        return {"data": [payload]}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch purchase request detail: {str(exc)}")
    finally:
        if cur is not None:
            cur.close()
        if con is not None:
            con.close()


@router.post("/purchaserequest/detail-approval")
def update_purchase_request_detail_approval(
    payload: dict[str, Any] = Body(default={}),
    _: None = Depends(verify_api_keys),
):
    """Bulk update PH_PQDTL.UDF_PQAPPROVED values by detail key."""
    changes = payload.get("changes", []) if isinstance(payload, dict) else []
    if not isinstance(changes, list) or not changes:
        raise HTTPException(status_code=400, detail="changes[] is required")

    con = None
    cur = None
    try:
        con = _connect_db()
        cur = con.cursor()
        detail_cols = _get_table_columns(cur, "PH_PQDTL")
        detail_key_col = _pick_existing(detail_cols, "DTLKEY", "PQDTLKEY", "ID")
        approved_col = _pick_existing(detail_cols, "UDF_PQAPPROVED")

        if not detail_key_col:
            raise HTTPException(status_code=500, detail="PH_PQDTL key column not found")
        if not approved_col:
            raise HTTPException(status_code=500, detail="PH_PQDTL.UDF_PQAPPROVED column not found")

        updated = 0
        for raw in changes:
            if not isinstance(raw, dict):
                continue
            if raw.get("detailId") is None:
                continue
            try:
                detail_id = int(raw.get("detailId"))
            except Exception:
                continue

            approved = bool(raw.get("approved"))
            encoded_value = _encode_bool_for_column(cur, "PH_PQDTL", approved_col, approved)

            cur.execute(
                f"UPDATE PH_PQDTL SET {approved_col} = ? WHERE {detail_key_col} = ?",
                (encoded_value, detail_id),
            )
            updated += int(cur.rowcount or 0)

        con.commit()
        return {
            "success": True,
            "updated": updated,
            "requested": len(changes),
        }
    except HTTPException:
        if con is not None:
            con.rollback()
        raise
    except Exception as exc:
        if con is not None:
            con.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update detail approval: {str(exc)}")
    finally:
        if cur is not None:
            cur.close()
        if con is not None:
            con.close()


@router.post("/purchaserequest/header-status")
def update_purchase_request_header_status(
    payload: dict[str, Any] = Body(default={}),
    _: None = Depends(verify_api_keys),
):
    """Bulk update PH_PQ.UDF_STATUS values by request id."""
    changes = payload.get("changes", []) if isinstance(payload, dict) else []
    if not isinstance(changes, list) or not changes:
        raise HTTPException(status_code=400, detail="changes[] is required")

    allowed = {"ACTIVE", "INACTIVE", "PENDING"}

    con = None
    cur = None
    try:
        con = _connect_db()
        cur = con.cursor()
        header_cols = _get_table_columns(cur, "PH_PQ")
        key_col = _pick_existing(header_cols, "DOCKEY", "PQKEY", "ID")
        udf_status_col = _pick_existing(header_cols, "UDF_STATUS")

        if not key_col:
            raise HTTPException(status_code=500, detail="PH_PQ key column not found")
        if not udf_status_col:
            raise HTTPException(status_code=500, detail="PH_PQ.UDF_STATUS column not found")

        updated = 0
        for raw in changes:
            if not isinstance(raw, dict):
                continue
            if raw.get("requestId") is None:
                continue

            try:
                request_id = int(raw.get("requestId"))
            except Exception:
                continue

            status_value = str(raw.get("udfStatus") or "").strip().upper()
            if status_value not in allowed:
                continue

            cur.execute(
                f"UPDATE PH_PQ SET {udf_status_col} = ? WHERE {key_col} = ?",
                (status_value, request_id),
            )
            updated += int(cur.rowcount or 0)

        con.commit()
        return {
            "success": True,
            "updated": updated,
            "requested": len(changes),
        }
    except HTTPException:
        if con is not None:
            con.rollback()
        raise
    except Exception as exc:
        if con is not None:
            con.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update header status: {str(exc)}")
    finally:
        if cur is not None:
            cur.close()
        if con is not None:
            con.close()
