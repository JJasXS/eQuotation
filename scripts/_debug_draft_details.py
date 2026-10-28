"""Debug SL_QTDRAFT detail load for a dockey (default 1)."""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Apps path preferred for running service parity
apps = r'C:\Apps\eQuotation'
if os.path.isdir(apps):
    sys.path.insert(0, apps)

from dotenv import load_dotenv

load_dotenv(os.path.join(apps, '.env'))
from utils.tenant_bootstrap import apply_tenant_env_overrides
from utils.db_utils import get_db_connection, set_db_config

apply_tenant_env_overrides()
set_db_config(os.getenv('DB_PATH'), os.getenv('DB_USER'), os.getenv('DB_PASSWORD'), os.getenv('DB_HOST'))

import main as m

dockey = int(sys.argv[1] if len(sys.argv) > 1 else 1)
con = get_db_connection()
cur = con.cursor()
cur.execute(
    """
    SELECT TRIM(RF.RDB$FIELD_NAME)
    FROM RDB$RELATION_FIELDS RF
    WHERE TRIM(RF.RDB$RELATION_NAME) = 'SL_QTDTLDRAFT'
    """
)
dtl_columns = {str(r[0]).strip() for r in (cur.fetchall() or []) if r and r[0]}
item_fields = m._quotation_line_item_fields_for_select(dtl_columns)
missing = [f for f in item_fields if f not in dtl_columns]
print('FIELDS', item_fields)
print('MISSING_FROM_TABLE', missing)
sql = f"SELECT {', '.join(item_fields)} FROM SL_QTDTLDRAFT WHERE DOCKEY = ? ORDER BY SEQ"
try:
    cur.execute(sql, (dockey,))
    rows = cur.fetchall() or []
    print('ROWS', len(rows))
    items = []
    for row in rows:
        row_map = {item_fields[i]: row[i] for i in range(len(item_fields))}
        items.append(m._quotation_line_item_from_row(row_map, cur=cur))
    print(json.dumps({'success': True, 'items': items}, default=str, indent=2)[:2000])
except Exception as exc:
    print('QUERY_FAIL', type(exc).__name__, exc)
cur.close()
con.close()
