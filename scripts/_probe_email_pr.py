"""Probe latest PR selected suppliers and AP_SUPPLIER email fields."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
apps = r"C:\Apps\eQuotation"
if os.path.isdir(apps):
    sys.path.insert(0, apps)

from dotenv import load_dotenv

load_dotenv(os.path.join(apps, ".env") if os.path.isdir(apps) else ".env", override=True)
from utils.db_utils import get_db_connection, set_db_config
from utils.tenant_bootstrap import apply_tenant_env_overrides

apply_tenant_env_overrides()
set_db_config(os.getenv("DB_PATH"), os.getenv("DB_USER"), os.getenv("DB_PASSWORD"), os.getenv("DB_HOST"))

con = get_db_connection()
cur = con.cursor()
cur.execute("SELECT FIRST 5 DOCKEY, DOCNO, UDF_STATUS FROM PH_PQ ORDER BY DOCKEY DESC")
print("LATEST_PRS", cur.fetchall())
cur.execute(
    "SELECT FIRST 30 ID, REQUEST_DOCKEY, REQUEST_NO, SUPPLIER_CODE, SUPPLIER_EMAIL "
    "FROM PR_SELECTED_SUPPLIER ORDER BY ID DESC"
)
print("SELECTED", cur.fetchall())
cur.execute(
    "SELECT TRIM(RF.RDB$FIELD_NAME) FROM RDB$RELATION_FIELDS RF "
    "WHERE TRIM(RF.RDB$RELATION_NAME)='AP_SUPPLIER'"
)
cols = sorted({str(r[0]).strip().upper() for r in cur.fetchall() if r and r[0]})
email_cols = [c for c in cols if "MAIL" in c or c.startswith("UDF_E")]
print("AP_SUPPLIER email-ish cols", email_cols)
pick = [c for c in ("CODE", "COMPANYNAME", "EMAIL", "UDF_EMAIL", "UDF_EMAIL01", "UDF_EMAIL1") if c in cols]
if pick:
    sql = f"SELECT FIRST 10 {', '.join(pick)} FROM AP_SUPPLIER"
    cur.execute(sql)
    print("SAMPLE_SUPPLIERS", cur.fetchall())
con.close()
