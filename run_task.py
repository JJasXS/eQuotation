import os
import sys
from decimal import Decimal
from datetime import date
from dotenv import load_dotenv

# Ensure we can import from the current directory
sys.path.append(os.getcwd())

# Load environment variables from .env
load_dotenv()

from utils.procurement_purchase_request import create_purchase_request
from utils.db_utils import get_db_connection, set_db_config

# Initialize database configuration
set_db_config(
    db_path=os.getenv("DB_PATH"),
    db_user=os.getenv("DB_USER"),
    db_password=os.getenv("DB_PASSWORD"),
    db_host=os.getenv("DB_HOST")
)

# Payload with required dates
today = date.today().isoformat()
payload = {
    'requesterId': 'REQ-01',
    'departmentId': 'DEPT-01',
    'requestDate': today,
    'requiredDate': today,
    'project': 'PRJ-MANUAL-01',
    'totalAmount': 100.0,
    'lineItems': [
        {
            'itemCode': 'ITEM-01',
            'itemName': 'Item 01',
            'project': 'PRJ-LINE-01',
            'quantity': 1,
            'unitPrice': 100.0,
            'tax': 0.0
        }
    ]
}

try:
    # 1) Call create_purchase_request
    print("Creating purchase request...")
    result = create_purchase_request(payload, created_by='sqlsupport')
    dockey = result.get('dockey')
    
    if not dockey:
        print("Error: No dockey returned in result")
        print(result)
        sys.exit(1)
    
    print(f"Created PR with DOCKEY: {dockey}")
    
    # 2) Query PH_PQ and PH_PQDTL
    con = get_db_connection()
    cur = con.cursor()
    
    # Query Header
    cur.execute("SELECT PROJECT FROM PH_PQ WHERE DOCKEY = ?", (dockey,))
    header_row = cur.fetchone()
    header_project = header_row[0].strip() if header_row and header_row[0] else "NOT FOUND"
    
    # Query Detail
    cur.execute("SELECT FIRST 1 PROJECT FROM PH_PQDTL WHERE DOCKEY = ?", (dockey,))
    detail_row = cur.fetchone()
    detail_project = detail_row[0].strip() if detail_row and detail_row[0] else "NOT FOUND"
    
    print(f"Header PROJECT: {header_project}")
    print(f"First Detail PROJECT: {detail_project}")
    
    con.close()

except Exception as e:
    print(f"An error occurred: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
