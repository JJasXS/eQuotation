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

payload = {
    "requesterId": "U001",
    "departmentId": "IT",
    "costCenter": "IT-OPS",
    "supplierId": "SUP-001",
    "currency": "MYR",
    "requestDate": "2026-04-21",
    "requiredDate": "2026-04-29",
    "justification": "Test Project Mapping",
    "deliveryLocation": "HQ Main Store",
    "notes": "Generated for project mapping test",
    "status": 0,
    "totalAmount": 100.0,
    "project": "",  # Header project=''
    "lineItems": [
        {
            "itemCode": "ITM-001",
            "itemName": "Test Item",
            "description": "Test Item Description",
            "quantity": 1,
            "unitPrice": 100,
            "tax": 0,
            "amount": 100,
            "project": "", # First detail project=''
        }
    ],
}

try:
    result = create_purchase_request(payload, "sqlsupport")
    dockey = result.get("dockey")
    if not dockey:
        print(f"Error: No dockey returned. Result: {result}")
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
    
    print(f"PH_PQ.PROJECT: '{header_project[0] if header_project else 'None'}'")
    print(f"PH_PQDTL.PROJECT: '{detail_project[0] if detail_project else 'None'}'")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
