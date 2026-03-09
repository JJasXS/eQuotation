import fdb


def _execute_ddl(conn, sql, success_message=None, ignore_if_contains=None):
    ignore_if_contains = ignore_if_contains or []
    cur = conn.cursor()
    try:
        cur.execute(sql)
        conn.commit()
        if success_message:
            print(success_message)
    except Exception as e:
        error_text = str(e).lower()
        if any(token.lower() in error_text for token in ignore_if_contains):
            return
        print(f"[DB INIT ERROR] {e}")
    finally:
        cur.close()


def _count_orphan_sl_qtdtl_rows(conn):
    cur = conn.cursor()
    try:
        cur.execute(
            '''
            SELECT COUNT(*)
            FROM SL_QTDTL d
            LEFT JOIN SL_QT h ON d.DOCKEY = h.DOCKEY
            WHERE h.DOCKEY IS NULL
            '''
        )
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception as e:
        print(f"[DB INIT WARNING] Unable to check orphan rows for FK_SL_QTDTL_QT: {e}")
        return None
    finally:
        cur.close()


def _ensure_sl_qt_status_column(conn):
    """Ensure SL_QT table has a STATUS column."""
    cur = conn.cursor()
    try:
        # Check if STATUS column already exists
        cur.execute(
            '''
            SELECT f.RDB$FIELD_NAME
            FROM RDB$RELATION_FIELDS f
            WHERE f.RDB$RELATION_NAME = 'SL_QT' AND f.RDB$FIELD_NAME = 'STATUS'
            '''
        )
        result = cur.fetchone()
        if result:
            print("[DB INIT] STATUS column already exists in SL_QT")
            return True
        
        # Add STATUS column if it doesn't exist
        conn.commit()
        cur.execute('ALTER TABLE SL_QT ADD STATUS VARCHAR(50)')
        conn.commit()
        print("[DB INIT] STATUS column added to SL_QT")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'duplicate' in error_msg:
            print("[DB INIT] STATUS column already exists in SL_QT")
            return True
        print(f"[DB INIT WARNING] Could not add STATUS to SL_QT: {e}")
        return False
    finally:
        cur.close()


def _ensure_sl_qt_terms_column(conn):
    """Ensure SL_QT table has a TERMS column."""
    cur = conn.cursor()
    try:
        # Check if TERMS column already exists
        cur.execute(
            '''
            SELECT f.RDB$FIELD_NAME
            FROM RDB$RELATION_FIELDS f
            WHERE f.RDB$RELATION_NAME = 'SL_QT' AND f.RDB$FIELD_NAME = 'TERMS'
            '''
        )
        result = cur.fetchone()
        if result:
            print("[DB INIT] TERMS column already exists in SL_QT")
            return True
        
        # Add TERMS column if it doesn't exist
        conn.commit()
        cur.execute('ALTER TABLE SL_QT ADD TERMS VARCHAR(100)')
        conn.commit()
        print("[DB INIT] TERMS column added to SL_QT")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'duplicate' in error_msg:
            print("[DB INIT] TERMS column already exists in SL_QT")
            return True
        print(f"[DB INIT WARNING] Could not add TERMS to SL_QT: {e}")
        return False
    finally:
        cur.close()


def _ensure_ar_customer_udf_email_column(conn):
    """Ensure AR_CUSTOMER table has UDF_EMAIL column for guest sign-in flow."""
    cur = conn.cursor()
    try:
        cur.execute(
            '''
            SELECT f.RDB$FIELD_NAME
            FROM RDB$RELATION_FIELDS f
            WHERE f.RDB$RELATION_NAME = 'AR_CUSTOMER' AND f.RDB$FIELD_NAME = 'UDF_EMAIL'
            '''
        )
        result = cur.fetchone()
        if result:
            print("[DB INIT] UDF_EMAIL column already exists in AR_CUSTOMER")
            return True

        conn.commit()
        cur.execute('ALTER TABLE AR_CUSTOMER ADD UDF_EMAIL VARCHAR(255)')
        conn.commit()
        print("[DB INIT] UDF_EMAIL column added to AR_CUSTOMER")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'duplicate' in error_msg:
            print("[DB INIT] UDF_EMAIL column already exists in AR_CUSTOMER")
            return True
        print(f"[DB INIT WARNING] Could not add UDF_EMAIL to AR_CUSTOMER: {e}")
        return False
    finally:
        cur.close()


def _backfill_udf_email_from_branch_email(conn):
    """
    One-time backfill from AR_CUSTOMERBRANCH.EMAIL to AR_CUSTOMER.UDF_EMAIL.
    Uses ROW_NUMBER to pick the first non-null EMAIL per customer CODE.
    """
    cur = conn.cursor()
    try:
        backfill_sql = """
        UPDATE AR_CUSTOMER c
        SET c.UDF_EMAIL = (
            SELECT e.EMAIL
            FROM (
                SELECT 
                    b.CODE,
                    b.EMAIL,
                    ROW_NUMBER() OVER (PARTITION BY b.CODE ORDER BY 
                        CASE WHEN b.EMAIL IS NOT NULL THEN 0 ELSE 1 END,
                        b.CODE) AS rn
                FROM AR_CUSTOMERBRANCH b
                WHERE b.EMAIL IS NOT NULL AND b.EMAIL <> ''
            ) e
            WHERE e.CODE = c.CODE AND e.rn = 1
        )
        WHERE c.CODE IN (
            SELECT DISTINCT b.CODE
            FROM AR_CUSTOMERBRANCH b
            WHERE b.EMAIL IS NOT NULL AND b.EMAIL <> ''
        )
        AND (c.UDF_EMAIL IS NULL OR c.UDF_EMAIL = '')
        """
        cur.execute(backfill_sql)
        conn.commit()
        print("[DB INIT] Backfilled AR_CUSTOMER.UDF_EMAIL from AR_CUSTOMERBRANCH.EMAIL")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        # It's okay if no rows match or column doesn't exist yet
        if 'column unknown' in error_msg or 'no rows' in error_msg:
            print("[DB INIT] Backfill not needed or columns not ready")
            return True
        print(f"[DB INIT WARNING] Backfill attempt: {e}")
        return False
    finally:
        cur.close()


def _ensure_email_sync_trigger(conn):
    """
    Drop and recreate trigger to sync AR_CUSTOMERBRANCH.EMAIL changes to AR_CUSTOMER.UDF_EMAIL.
    Then sync to OWNEREMAIL in CHAT_TPL and ORDER_TPL.
    """
    cur = conn.cursor()
    try:
        # Drop trigger if exists (to allow re-creation)
        try:
            cur.execute("DROP TRIGGER TRG_SYNC_CUSTOMERBRANCH_EMAIL")
            conn.commit()
        except:
            pass  # Trigger doesn't exist, that's fine
        
        # Create trigger that syncs EMAIL to UDF_EMAIL and downstream tables
        trigger_sql = """
        CREATE TRIGGER TRG_SYNC_CUSTOMERBRANCH_EMAIL FOR AR_CUSTOMERBRANCH
        ACTIVE AFTER INSERT, UPDATE POSITION 0
        AS
        BEGIN
          /* Sync EMAIL to AR_CUSTOMER.UDF_EMAIL */
          UPDATE AR_CUSTOMER c
          SET c.UDF_EMAIL = NEW.EMAIL
          WHERE c.CODE = NEW.CODE
            AND (c.UDF_EMAIL IS NULL OR c.UDF_EMAIL <> NEW.EMAIL)
            AND NEW.EMAIL IS NOT NULL;
          
          /* Sync to OWNEREMAIL in CHAT_TPL */
          UPDATE CHAT_TPL
          SET OWNEREMAIL = NEW.EMAIL
          WHERE CUSTOMERCODE = NEW.CODE
            AND NEW.EMAIL IS NOT NULL;
          
          /* Sync to OWNEREMAIL in ORDER_TPL */
          UPDATE ORDER_TPL
          SET OWNEREMAIL = NEW.EMAIL
          WHERE CUSTOMERCODE = NEW.CODE
            AND NEW.EMAIL IS NOT NULL;
        END
        """
        cur.execute(trigger_sql)
        conn.commit()
        print("[DB INIT] Email sync trigger TRG_SYNC_CUSTOMERBRANCH_EMAIL created successfully")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'name in use' in error_msg:
            print("[DB INIT] Email sync trigger already exists")
            return True
        print(f"[DB INIT WARNING] Could not create email sync trigger: {e}")
        return False
    finally:
        cur.close()


def initialize_database(db_path, db_user, db_password):
    conn = None
    try:
        conn = fdb.connect(
            dsn=db_path,
            user=db_user,
            password=db_password,
            charset='UTF8'
        )

        _execute_ddl(
            conn,
            """
            CREATE TABLE CHAT_TPL (
                CHATID INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                CHATNAME VARCHAR(100) NOT NULL,
                CREATEDAT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                LASTMESSAGE VARCHAR(255),
                OWNEREMAIL VARCHAR(400),
                CUSTOMERCODE VARCHAR(20)
            )
            """,
            success_message='[DB INIT] CHAT_TPL table created.',
            ignore_if_contains=['table unknown', 'already exists', 'name in use']
        )

        _execute_ddl(
            conn,
            """
            CREATE TABLE CHAT_TPLDTL (
                MESSAGEID INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                CHATID INTEGER NOT NULL,
                SENDER VARCHAR(100) NOT NULL,
                MESSAGETEXT VARCHAR(4000) NOT NULL,
                SENTAT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (CHATID) REFERENCES CHAT_TPL(CHATID)
            )
            """,
            success_message='[DB INIT] CHAT_TPLDTL table created.',
            ignore_if_contains=['table unknown', 'already exists', 'name in use']
        )

        _execute_ddl(
            conn,
            """
            CREATE TABLE ORDER_TPL (
                ORDERID INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                CHATID INTEGER NOT NULL,
                OWNEREMAIL VARCHAR(400),
                CUSTOMERCODE VARCHAR(20),
                STATUS VARCHAR(50),
                CREATEDAT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (CHATID) REFERENCES CHAT_TPL(CHATID)
            )
            """,
            success_message='[DB INIT] ORDER_TPL table created.',
            ignore_if_contains=['table unknown', 'already exists', 'name in use']
        )

        _execute_ddl(
            conn,
            """
            CREATE TABLE ORDER_TPLDTL (
                ORDERDTLID INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                ORDERID INTEGER NOT NULL,
                DESCRIPTION VARCHAR(255) NOT NULL,
                QTY INTEGER NOT NULL,
                UNITPRICE DECIMAL(18,2) NOT NULL,
                TOTAL DECIMAL(18,2) NOT NULL,
                DISCOUNT DECIMAL(5,2) DEFAULT 0,
                FOREIGN KEY (ORDERID) REFERENCES ORDER_TPL(ORDERID)
            )
            """,
            success_message='[DB INIT] ORDER_TPLDTL table created.',
            ignore_if_contains=['table unknown', 'already exists', 'name in use']
        )

        _execute_ddl(
            conn,
            """
            CREATE TABLE ORDER_REMARK_TPL (
                REMARKID INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                ORDERID INTEGER NOT NULL,
                REMARK VARCHAR(1000) NOT NULL,
                REQUESTEDBY VARCHAR(400),
                REMARKTYPE VARCHAR(50),
                CREATEDAT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ORDERID) REFERENCES ORDER_TPL(ORDERID)
            )
            """,
            success_message='[DB INIT] ORDER_REMARK_TPL table created.',
            ignore_if_contains=['table unknown', 'already exists', 'name in use']
        )

        # NOTE:
        # Auto-creating FK_SL_QTDTL_QT is disabled to avoid startup failures
        # on accounting databases that contain historical orphan rows.
        print("[DB INIT WARNING] FK_SL_QTDTL_QT auto-creation is skipped.")

        # Ensure SL_QT has STATUS column for quotation lifecycle
        _ensure_sl_qt_status_column(conn)
        
        # Ensure SL_QT has TERMS column to store payment terms
        _ensure_sl_qt_terms_column(conn)

        # Ensure AR_CUSTOMER has UDF_EMAIL for guest sign-in payload
        _ensure_ar_customer_udf_email_column(conn)
        
        # One-time backfill from AR_CUSTOMERBRANCH.EMAIL to AR_CUSTOMER.UDF_EMAIL
        _backfill_udf_email_from_branch_email(conn)
        
        # Create trigger to sync AR_CUSTOMERBRANCH.EMAIL to UDF_EMAIL and downstream tables
        _ensure_email_sync_trigger(conn)

    except Exception as e:
        print(f"[DB INIT ERROR] {e}")
    finally:
        if conn:
            conn.close()
