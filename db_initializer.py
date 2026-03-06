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


def _ensure_email_sync_trigger(conn):
    """
    Create trigger to sync AR_CUSTOMERBRANCH.EMAIL changes to OWNEREMAIL in CHAT_TPL and ORDER_TPL.
    When AR_CUSTOMERBRANCH.EMAIL is updated, automatically update all related OWNEREMAIL fields.
    """
    cur = conn.cursor()
    try:
        # Drop trigger if exists (to allow re-creation)
        try:
            cur.execute("DROP TRIGGER TRG_SYNC_CUSTOMER_EMAIL")
            conn.commit()
        except:
            pass  # Trigger doesn't exist, that's fine
        
        # Create trigger
        trigger_sql = """
        CREATE TRIGGER TRG_SYNC_CUSTOMER_EMAIL FOR AR_CUSTOMERBRANCH
        ACTIVE AFTER UPDATE POSITION 0
        AS
        BEGIN
          /* If EMAIL column was updated, sync to related tables */
          IF (NEW.EMAIL IS DISTINCT FROM OLD.EMAIL) THEN
          BEGIN
            /* Update OWNEREMAIL in CHAT_TPL for this customer */
            UPDATE CHAT_TPL
            SET OWNEREMAIL = NEW.EMAIL
            WHERE CUSTOMERCODE = NEW.CODE;
            
            /* Update OWNEREMAIL in ORDER_TPL for this customer */
            UPDATE ORDER_TPL
            SET OWNEREMAIL = NEW.EMAIL
            WHERE CUSTOMERCODE = NEW.CODE;
          END
        END
        """
        cur.execute(trigger_sql)
        conn.commit()
        print("[DB INIT] Email sync trigger TRG_SYNC_CUSTOMER_EMAIL created successfully")
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
        
        # Create trigger to sync AR_CUSTOMERBRANCH.EMAIL to OWNEREMAIL fields
        _ensure_email_sync_trigger(conn)

    except Exception as e:
        print(f"[DB INIT ERROR] {e}")
    finally:
        if conn:
            conn.close()
