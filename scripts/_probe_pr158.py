import os
import sys

sys.path.insert(0, r"C:\Apps\eQuotation")
from dotenv import load_dotenv

load_dotenv(r"C:\Apps\eQuotation\.env", override=True)
from utils.tenant_bootstrap import apply_tenant_env_overrides
from utils.db_utils import get_db_connection, set_db_config

apply_tenant_env_overrides()
set_db_config(os.getenv("DB_PATH"), os.getenv("DB_USER"), os.getenv("DB_PASSWORD"), os.getenv("DB_HOST"))
con = get_db_connection()
cur = con.cursor()
cur.execute(
    "SELECT DOCKEY, DOCNO, UDF_STATUS, CODE, COMPANYNAME FROM PH_PQ "
    "WHERE DOCKEY = ? OR DOCNO = ?",
    (158, "PR-26100044"),
)
print("HEADER", cur.fetchall())
cur.execute(
    "SELECT ID, REQUEST_DOCKEY, REQUEST_NO, SUPPLIER_CODE, SUPPLIER_NAME, SUPPLIER_EMAIL "
    "FROM PR_SELECTED_SUPPLIER WHERE REQUEST_DOCKEY = ? OR REQUEST_NO = ?",
    (158, "PR-26100044"),
)
print("SELECTED", cur.fetchall())
cur.execute("SELECT COALESCE(MAX(ID), 0) FROM PR_SELECTED_SUPPLIER")
print("MAX_ID", cur.fetchone())
try:
    cur.execute("SELECT GEN_ID(GEN_PR_SELECTED_SUPPLIER_ID, 0) FROM RDB$DATABASE")
    print("GEN", cur.fetchone())
except Exception as exc:
    print("GEN_ERR", exc)
con.close()
