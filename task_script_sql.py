import json
import sys
import os
from datetime import datetime
from dotenv import load_dotenv

# Add the current directory to sys.path so we can import utils
sys.path.append(os.getcwd())

from utils.db_utils import set_db_config, get_db_connection
from utils.procurement_purchase_request import create_purchase_request

# Load environment variables
load_dotenv()

# Initialize DB config
set_db_config(
    os.getenv("DB_PATH"),
    os.getenv("DB_USER"),
    os.getenv("DB_PASSWORD"),
    os.getenv("DB_HOST")
)

# SQL-style payload where sdsdocdetail triggers _normalize_sql_api_payload
payload = {
    "docno": "SQL-PR-TEST-001",
    "docdate": "2026-04-21",
    "postdate": "2026-04-29",
    "agent": "SUP-001",
    "project": "",  # header project=''
    "currencycode": "MYR",
    "description": "SQL-style payload mapping test",
    "sdsdocdetail": [
        {
            "itemcode": "ITM-001",
            "qty": 1,
            "unitprice": 100,
            "project": "", # first detail project=''
        }
    ],
}

try:
    result = create_purchase_request(payload, "sqlsupport")
    dockey = result.get("id") # The function returns 'id' as the generated dockey
    if not dockey:
        print(f"Error: No id (dockey) returned. Result: {result}")
        sys.exit(1)
    
    print(f"Created DOCKEY: {dockey}")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Query PH_PQ.PROJECT
    cursor.execute("SELECT PROJECT FROM PH_PQ WHERE DOCKEY = ?", (dockey,))
    header_project = cursor.fetchone()
    
    # Query PH_PQDTL.PROJECT
    cursor.execute("SELECT PROJECT FROM PH_PQDTL WHERE DOCKEY = ?", (dockey,))
    detail_project = cursor.fetchone()
    
    # Format output for empty strings to make them visible
    h_val = header_project[0] if header_project else 'None'
    d_val = detail_project[0] if detail_project else 'None'
    
    print(f"PH_PQ.PROJECT: '{h_val}'")
    print(f"PH_PQDTL.PROJECT: '{d_val}'")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
