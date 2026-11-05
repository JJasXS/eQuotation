"""Probe PR-26100045 / dockey 159 for RFQ invite diagnosis."""
import os
from dotenv import load_dotenv

load_dotenv(r"C:\Apps\eQuotation\.env", override=True)
from utils.tenant_bootstrap import apply_tenant_env_overrides
from utils.db_utils import get_db_connection, set_db_config

apply_tenant_env_overrides()
set_db_config(os.getenv("DB_PATH"), os.getenv("DB_USER"), os.getenv("DB_PASSWORD"), os.getenv("DB_HOST"))
con = get_db_connection()
cur = con.cursor()


def show(title, sql, params=()):
    print(f"\n=== {title} ===")
    try:
        cur.execute(sql, params)
        cols = [d[0].strip() if isinstance(d[0], str) else d[0] for d in (cur.description or [])]
        rows = cur.fetchall()
        print("cols:", cols)
        if not rows:
            print("(no rows)")
        for r in rows:
            print(dict(zip(cols, r)) if cols else r)
    except Exception as exc:
        print("ERR:", exc)
        con.rollback()


show(
    "PH_PQ header 159 / PR-26100045",
    """
    SELECT DOCKEY, DOCNO, STATUS, UDF_STATUS, DOCDATE, DESCRIPTION
    FROM PH_PQ
    WHERE DOCKEY = ? OR DOCNO = ?
    """,
    (159, "PR-26100045"),
)

show(
    "PR_SELECTED_SUPPLIER for 159",
    """
    SELECT ID, REQUEST_DOCKEY, REQUEST_NO, SUPPLIER_CODE, SUPPLIER_NAME, EMAIL, CREATED_AT
    FROM PR_SELECTED_SUPPLIER
    WHERE REQUEST_DOCKEY = ? OR REQUEST_NO = ?
    ORDER BY ID
    """,
    (159, "PR-26100045"),
)

show(
    "PR_BID_INVITE for 159",
    """
    SELECT *
    FROM PR_BID_INVITE
    WHERE REQUEST_DOCKEY = ? OR REQUEST_NO = ?
    ORDER BY INVITE_ID
    """,
    (159, "PR-26100045"),
)

show(
    "PR_BID_HDR for 159",
    """
    SELECT BID_ID, REQUEST_DOCKEY, SUPPLIER_CODE, STATUS, CREATED_AT
    FROM PR_BID_HDR
    WHERE REQUEST_DOCKEY = ?
    """,
    (159,),
)

show(
    "PH_PQDTL lines for 159",
    """
    SELECT DTLKEY, DOCKEY, ITEMCODE, DESCRIPTION, QTY
    FROM PH_PQDTL
    WHERE DOCKEY = ?
    """,
    (159,),
)
