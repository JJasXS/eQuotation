"""Database utility functions for Firebird database operations."""
import fdb

# Database configuration (will be set from main.py)
DB_PATH = None
DB_HOST = None
DB_USER = None
DB_PASSWORD = None


def build_firebird_dsn(db_path, db_host=None):
    """Build a Firebird DSN from optional host and required database path."""
    if not db_path:
        raise ValueError("DB_PATH is not configured.")

    cleaned_path = db_path.strip()
    cleaned_host = (db_host or '').strip()

    if not cleaned_host:
        return cleaned_path

    # Firebird remote DSN works reliably with forward slashes in Windows paths.
    normalized_path = cleaned_path.replace('\\', '/')
    return f"{cleaned_host}:{normalized_path}"


def set_db_config(db_path, db_user, db_password, db_host=None):
    """Set database configuration."""
    global DB_PATH, DB_HOST, DB_USER, DB_PASSWORD
    DB_PATH = db_path
    DB_HOST = db_host
    DB_USER = db_user
    DB_PASSWORD = db_password


def get_db_connection():
    """Get a Firebird database connection."""
    return fdb.connect(
        dsn=build_firebird_dsn(DB_PATH, DB_HOST),
        user=DB_USER,
        password=DB_PASSWORD,
        charset='UTF8'
    )


def user_owns_chat(chatid, user_email):
    """Check whether a chat belongs to the logged-in user."""
    con = None
    cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute('SELECT CHATID FROM CHAT_TPL WHERE CHATID = ? AND OWNEREMAIL = ?', (chatid, user_email))
        return cur.fetchone() is not None
    except Exception as e:
        print(f"Failed to verify chat ownership: {e}")
        return False
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


def get_chat_history(chatid, user_email=None):
    """Get chat history for a given chat ID."""
    con = None
    cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()
        if user_email:
            cur.execute(
                'SELECT d.MESSAGEID, d.CHATID, d.SENDER, d.MESSAGETEXT, d.SENTAT '
                'FROM CHAT_TPLDTL d '
                'JOIN CHAT_TPL c ON c.CHATID = d.CHATID '
                'WHERE d.CHATID = ? AND c.OWNEREMAIL = ? '
                'ORDER BY d.SENTAT ASC',
                (chatid, user_email)
            )
        else:
            cur.execute(
                'SELECT MESSAGEID, CHATID, SENDER, MESSAGETEXT, SENTAT '
                'FROM CHAT_TPLDTL WHERE CHATID = ? ORDER BY SENTAT ASC',
                (chatid,)
            )

        return [
            {
                'MESSAGEID': row[0],
                'CHATID': row[1],
                'SENDER': row[2],
                'MESSAGETEXT': row[3],
                'SENTAT': row[4].strftime('%Y-%m-%d %H:%M:%S') if row[4] else None
            }
            for row in cur.fetchall()
        ]
    except Exception as e:
        print(f"Failed to fetch chat history: {e}")
    finally:
        if cur:
            cur.close()
        if con:
            con.close()
    return []


def update_chat_last_message(chatid, messagetext, user_email=None):
    """Update the last message in a chat."""
    con = get_db_connection()
    cur = con.cursor()
    try:
        if user_email:
            cur.execute(
                'UPDATE CHAT_TPL SET LASTMESSAGE = ? WHERE CHATID = ? AND OWNEREMAIL = ?',
                (messagetext, chatid, user_email)
            )
        else:
            cur.execute('UPDATE CHAT_TPL SET LASTMESSAGE = ? WHERE CHATID = ?', (messagetext, chatid))
        con.commit()
    finally:
        cur.close()
        con.close()


def get_active_order(chatid):
    """Get active DRAFT order for chat (only check, don't create)."""
    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute('SELECT ORDERID FROM ORDER_TPL WHERE CHATID = ? AND STATUS = ?', (chatid, 'DRAFT'))
        result = cur.fetchone()
        cur.close()
        con.close()
        
        if result:
            return result[0]
        else:
            return None
    except Exception as e:
        print(f"Error getting active order: {e}")
    return None


def test_firebird_connection():
    """Test Firebird database connection."""
    try:
        con = get_db_connection()
        con.close()
        print("Firebird database connection successful.")
    except Exception as e:
        print("Firebird database connection failed:", e)
