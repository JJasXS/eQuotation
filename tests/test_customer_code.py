"""
Quick test to verify CUSTOMERCODE is populated after login
Run this after creating a new chat to check if CUSTOMERCODE is stored
"""
import os
import fdb
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

DB_PATH = os.getenv('DB_PATH')
DB_USER = os.getenv('DB_USER', 'SYSDBA')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'masterkey')

if not DB_PATH:
    raise ValueError('DB_PATH is not set in .env')

try:
    con = fdb.connect(dsn=DB_PATH, user=DB_USER, password=DB_PASSWORD, charset='UTF8')
    cur = con.cursor()
    
    # Check most recent chat
    cur.execute('''
        SELECT CHATID, CHATNAME, OWNEREMAIL, CUSTOMERCODE, CREATEDAT 
        FROM CHAT_TPL 
        ORDER BY CREATEDAT DESC 
        FETCH FIRST 1 ROWS ONLY
    ''')
    
    chat = cur.fetchone()
    if chat:
        print("\n=== Most Recent Chat ===")
        print(f"CHATID: {chat[0]}")
        print(f"NAME: {chat[1]}")
        print(f"EMAIL: {chat[2]}")
        print(f"CUSTOMERCODE: {chat[3]}")
        print(f"CREATED: {chat[4]}")
        
        if chat[3]:
            print(f"\n✅ SUCCESS! CUSTOMERCODE is populated: {chat[3]}")
        else:
            print("\n❌ CUSTOMERCODE is NULL - Please logout and login again")
    
    # Check most recent order
    cur.execute('''
        SELECT ORDERID, CHATID, OWNEREMAIL, CUSTOMERCODE, STATUS 
        FROM ORDER_TPL 
        ORDER BY CREATEDAT DESC 
        FETCH FIRST 1 ROWS ONLY
    ''')
    
    order = cur.fetchone()
    if order:
        print("\n=== Most Recent Order ===")
        print(f"ORDERID: {order[0]}")
        print(f"CHATID: {order[1]}")
        print(f"EMAIL: {order[2]}")
        print(f"CUSTOMERCODE: {order[3]}")
        print(f"STATUS: {order[4]}")
        
        if order[3]:
            print(f"\n✅ SUCCESS! CUSTOMERCODE is populated: {order[3]}")
        else:
            print("\n❌ CUSTOMERCODE is NULL")
    
    cur.close()
    con.close()
    
except Exception as e:
    print(f"Error: {e}")
