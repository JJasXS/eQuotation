from dotenv import load_dotenv
load_dotenv()
import os, fdb

conn = fdb.connect(dsn=os.getenv('DB_PATH'), user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'), charset='UTF8')
cur = conn.cursor()

# AR_CUSTOMER - find price tag related columns
cur.execute("SELECT RDB$FIELD_NAME FROM RDB$RELATION_FIELDS WHERE RDB$RELATION_NAME = 'AR_CUSTOMER' ORDER BY RDB$FIELD_POSITION")
all_cols = [r[0].strip() for r in cur.fetchall()]
price_related = [c for c in all_cols if any(x in c.upper() for x in ['PRICE', 'TAG', 'CAT', 'LEVEL', 'DISC'])]
print('AR_CUSTOMER price-related columns:', price_related)

# Also check customer price tag value for a sample customer
cur.execute("SELECT FIRST 5 CODE FROM AR_CUSTOMER")
customers = [r[0] for r in cur.fetchall()]
print('Sample customer codes:', customers)
if customers and price_related:
    for col in price_related:
        try:
            cur.execute(f"SELECT FIRST 3 CODE, {col} FROM AR_CUSTOMER WHERE {col} IS NOT NULL AND TRIM(CAST({col} AS VARCHAR(100))) <> ''")
            rows = cur.fetchall()
            if rows:
                print(f'  AR_CUSTOMER.{col} sample values: {rows}')
        except Exception as e:
            print(f'  AR_CUSTOMER.{col} error: {e}')

print()
# ST_ITEM_PRICE - all columns
cur.execute("SELECT RDB$FIELD_NAME FROM RDB$RELATION_FIELDS WHERE RDB$RELATION_NAME = 'ST_ITEM_PRICE' ORDER BY RDB$FIELD_POSITION")
cols2 = [r[0].strip() for r in cur.fetchall()]
print('ST_ITEM_PRICE all columns:', cols2)

# Show sample data
try:
    cur.execute("SELECT FIRST 3 * FROM ST_ITEM_PRICE WHERE STOCKVALUE IS NOT NULL")
    rows = cur.fetchall()
    print('ST_ITEM_PRICE sample rows:')
    for r in rows:
        print(' ', r)
except Exception as e:
    print('ST_ITEM_PRICE sample error:', e)

cur.close()
conn.close()
