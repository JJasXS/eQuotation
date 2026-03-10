import os
import fdb
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

DB_PATH = os.getenv('DB_PATH')
DB_USER = os.getenv('DB_USER', 'SYSDBA')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'masterkey')

if not DB_PATH:
    raise ValueError('DB_PATH is not set in .env')

# Connect to database
con = fdb.connect(
    dsn=DB_PATH,
    user=DB_USER,
    password=DB_PASSWORD
)

cur = con.cursor()

# Query items with prices
cur.execute('''
    SELECT p.CODE, i.DESCRIPTION, p.STOCKVALUE 
    FROM ST_ITEM_PRICE p
    LEFT JOIN ST_ITEM i ON p.CODE = i.CODE
    WHERE p.STOCKVALUE > 0 
    ORDER BY p.STOCKVALUE DESC 
    ROWS 20
''')

print("\n" + "="*130)
print(f"{'CODE':<20} {'DESCRIPTION':<80} {'PRICE':>20}")
print("="*130)

for row in cur.fetchall():
    code, desc, price = row
    desc_str = str(desc if desc else '') if desc else ''
    print(f"{str(code):<20} {desc_str:<80} {price:>20.2f}")

print("="*130)
con.close()
