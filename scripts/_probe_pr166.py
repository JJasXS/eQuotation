"""Probe PR-26100051 / dockey 166 for RFQ invite diagnosis."""
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
        if not rows:
            print("(no rows)")
        for r in rows:
            print(dict(zip(cols, r)) if cols else r)
    except Exception as exc:
        print("ERR:", exc)
        con.rollback()


cur.execute(
    "SELECT TRIM(RF.RDB$FIELD_NAME) FROM RDB$RELATION_FIELDS RF "
    "WHERE TRIM(RF.RDB$RELATION_NAME)='PR_SELECTED_SUPPLIER'"
)
print("PR_SELECTED_SUPPLIER cols", sorted(str(r[0]).strip() for r in cur.fetchall()))

show(
    "PH_PQ 166",
    "SELECT DOCKEY, DOCNO, STATUS, UDF_STATUS, CODE, COMPANYNAME FROM PH_PQ WHERE DOCKEY=? OR DOCNO=?",
    (166, "PR-26100051"),
)
show(
    "PR_SELECTED_SUPPLIER 166",
    "SELECT * FROM PR_SELECTED_SUPPLIER WHERE REQUEST_DOCKEY=? OR REQUEST_NO=? ORDER BY ID",
    (166, "PR-26100051"),
)
show(
    "PR_BID_INVITE 166",
    "SELECT INVITE_ID, REQUEST_DOCKEY, REQUEST_NO, SUPPLIER_CODE, STATUS, CREATED_AT "
    "FROM PR_BID_INVITE WHERE REQUEST_DOCKEY=? OR REQUEST_NO=? ORDER BY INVITE_ID",
    (166, "PR-26100051"),
)
show(
    "recent invites",
    "SELECT FIRST 15 INVITE_ID, REQUEST_DOCKEY, REQUEST_NO, SUPPLIER_CODE, STATUS, CREATED_AT "
    "FROM PR_BID_INVITE ORDER BY INVITE_ID DESC",
)
show(
    "lines 166",
    "SELECT DTLKEY, ITEMCODE, DESCRIPTION, QTY FROM PH_PQDTL WHERE DOCKEY=?",
    (166,),
)
con.close()
