import os
import fdb
from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

DB_PATH = os.getenv('DB_PATH')
DB_USER = os.getenv('DB_USER', 'sysdba')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'masterkey')

if not DB_PATH:
    raise ValueError('DB_PATH environment variable is not set. Please configure it in .env file.')

def initialize_database():
    """Initialize database schema - expand MESSAGETEXT field to support longer messages"""
    try:
        print("Connecting to Firebird database...")
        con = fdb.connect(
            dsn=DB_PATH,
            user=DB_USER,
            password=DB_PASSWORD,
            charset='UTF8'
        )
        cur = con.cursor()
        
        print("Altering CHAT_TPLDTL.MESSAGETEXT to support longer messages (4000 chars)...")
        cur.execute('ALTER TABLE CHAT_TPLDTL ALTER COLUMN MESSAGETEXT TYPE VARCHAR(4000)')
        con.commit()
        print("✓ Successfully updated MESSAGETEXT column to VARCHAR(4000)")
        
        print("\nAltering CHAT_TPL.LASTMESSAGE to support longer messages (4000 chars)...")
        cur.execute('ALTER TABLE CHAT_TPL ALTER COLUMN LASTMESSAGE TYPE VARCHAR(4000)')
        con.commit()
        print("✓ Successfully updated LASTMESSAGE column to VARCHAR(4000)")
        
        cur.close()
        con.close()
        
        print("\n✅ Database initialization complete!")
        print("You can now run main.py to start the chatbot.")
        
    except Exception as e:
        print(f"❌ Error during database initialization: {e}")
        print("\nNote: If columns are already the correct size, this is normal.")
        return False
    
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("DATABASE INITIALIZER - Chatbot Schema Update")
    print("=" * 60)
    print()
    initialize_database()
