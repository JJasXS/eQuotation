import fdb


PRICING_PRIORITY_RULE_DEFAULTS = [
    ('CUSTOMER_PRICE_TAG', 'Customer Price Tag', 1, 1),
    ('REF_PRICE_BASED_ON_UOM', 'Ref. Price of Item Based on UOM', 2, 1),
    ('MIN_MAX_SELLING_PRICE', 'Min & Max Selling Price', 3, 1),
    ('LAST_QUOTATION_SELLING_PRICE', 'Last Quotation Selling Price', 4, 1),
    ('LAST_SALES_ORDER_SELLING_PRICE', 'Last Sales Order Selling Price', 5, 1),
    ('LAST_SALES_DELIVERY_ORDER_SELLING_PRICE', 'Last Sales Delivery Order Selling Price', 6, 1),
    ('LAST_SALES_INVOICE_SELLING_PRICE', 'Last Sales Invoice Selling Price', 7, 1),
    ('LAST_CASH_SALES_SELLING_PRICE', 'Last Cash Sales Selling Price', 8, 1),
    ('LAST_SALES_INVOICE_CASH_SALES_SELLING_PRICE', 'Last Sales Invoice / Cash Sales Selling Price', 9, 1),
]


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
    Drop and recreate bi-directional email sync triggers:
    - AR_CUSTOMERBRANCH.EMAIL -> AR_CUSTOMER.UDF_EMAIL
    - AR_CUSTOMER.UDF_EMAIL -> AR_CUSTOMERBRANCH.EMAIL
    Also sync to OWNEREMAIL in CHAT_TPL and ORDER_TPL.
    """
    cur = conn.cursor()
    try:
        # Drop triggers if they exist (to allow re-creation)
        try:
            cur.execute("DROP TRIGGER TRG_SYNC_CUSTOMERBRANCH_EMAIL")
            conn.commit()
        except Exception:
            pass  # Trigger doesn't exist, that's fine

        try:
            cur.execute("DROP TRIGGER TRG_SYNC_CUSTOMER_UDF_EMAIL")
            conn.commit()
        except Exception:
            pass  # Trigger doesn't exist, that's fine

        # Sync branch email up to customer header and downstream owner email.
        branch_to_customer_trigger_sql = """
        CREATE TRIGGER TRG_SYNC_CUSTOMERBRANCH_EMAIL FOR AR_CUSTOMERBRANCH
        ACTIVE AFTER INSERT OR UPDATE POSITION 0
        AS
        BEGIN
          UPDATE AR_CUSTOMER c
          SET c.UDF_EMAIL = NEW.EMAIL
          WHERE c.CODE = NEW.CODE
            AND NEW.EMAIL IS NOT NULL
            AND (c.UDF_EMAIL IS NULL OR c.UDF_EMAIL <> NEW.EMAIL);

          UPDATE CHAT_TPL
          SET OWNEREMAIL = NEW.EMAIL
          WHERE CUSTOMERCODE = NEW.CODE
            AND NEW.EMAIL IS NOT NULL;

          UPDATE ORDER_TPL
          SET OWNEREMAIL = NEW.EMAIL
          WHERE CUSTOMERCODE = NEW.CODE
            AND NEW.EMAIL IS NOT NULL;
        END
        """
        cur.execute(branch_to_customer_trigger_sql)
        conn.commit()

        # Sync customer header email down to branches and downstream owner email.
        customer_to_branch_trigger_sql = """
        CREATE TRIGGER TRG_SYNC_CUSTOMER_UDF_EMAIL FOR AR_CUSTOMER
        ACTIVE AFTER INSERT OR UPDATE POSITION 0
        AS
        BEGIN
          UPDATE AR_CUSTOMERBRANCH b
          SET b.EMAIL = NEW.UDF_EMAIL
          WHERE b.CODE = NEW.CODE
            AND NEW.UDF_EMAIL IS NOT NULL
            AND (b.EMAIL IS NULL OR b.EMAIL <> NEW.UDF_EMAIL);

          UPDATE CHAT_TPL
          SET OWNEREMAIL = NEW.UDF_EMAIL
          WHERE CUSTOMERCODE = NEW.CODE
            AND NEW.UDF_EMAIL IS NOT NULL;

          UPDATE ORDER_TPL
          SET OWNEREMAIL = NEW.UDF_EMAIL
          WHERE CUSTOMERCODE = NEW.CODE
            AND NEW.UDF_EMAIL IS NOT NULL;
        END
        """
        cur.execute(customer_to_branch_trigger_sql)
        conn.commit()

        print("[DB INIT] Email sync triggers created: TRG_SYNC_CUSTOMERBRANCH_EMAIL, TRG_SYNC_CUSTOMER_UDF_EMAIL")
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


def _ensure_ar_customer_idno_from_brn2_trigger(conn):
    """Ensure AR_CUSTOMER.IDNO is auto-copied from BRN2 on insert/update."""
    cur = conn.cursor()
    try:
        try:
            cur.execute("DROP TRIGGER TRG_AR_CUSTOMER_BRN2_IDNO")
            conn.commit()
        except Exception:
            pass

        trigger_sql = """
        CREATE TRIGGER TRG_AR_CUSTOMER_BRN2_IDNO FOR AR_CUSTOMER
        ACTIVE BEFORE INSERT OR UPDATE POSITION 0
        AS
        BEGIN
          IF (NEW.BRN2 IS NOT NULL) THEN
            NEW.IDNO = NEW.BRN2;
        END
        """
        cur.execute(trigger_sql)
        conn.commit()
        print("[DB INIT] Trigger TRG_AR_CUSTOMER_BRN2_IDNO created successfully")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'name in use' in error_msg:
            print("[DB INIT] Trigger TRG_AR_CUSTOMER_BRN2_IDNO already exists")
            return True
        print(f"[DB INIT WARNING] Could not create BRN2->IDNO trigger: {e}")
        return False
    finally:
        cur.close()


def _ensure_ar_customerbranch_branchtype_branchname_trigger(conn):
    """
    Ensure AR_CUSTOMERBRANCH defaults/enforces:
    - BRANCHTYPE defaults to 'B' on INSERT when missing/blank
    - BRANCHNAME forced to 'BILLING' when BRANCHTYPE = 'B'
    """
    cur = conn.cursor()
    try:
        try:
            cur.execute("DROP TRIGGER TRG_AR_CUSTOMERBRANCH_BILLING")
            conn.commit()
        except Exception:
            pass

        trigger_sql = """
        CREATE TRIGGER TRG_AR_CUSTOMERBRANCH_BILLING FOR AR_CUSTOMERBRANCH
        ACTIVE BEFORE INSERT OR UPDATE POSITION 0
        AS
        BEGIN
          IF (INSERTING AND (NEW.BRANCHTYPE IS NULL OR TRIM(NEW.BRANCHTYPE) = '')) THEN
            NEW.BRANCHTYPE = 'B';

          IF (NEW.BRANCHTYPE = 'B') THEN
            NEW.BRANCHNAME = 'BILLING';
        END
        """
        cur.execute(trigger_sql)
        conn.commit()
        print("[DB INIT] Trigger TRG_AR_CUSTOMERBRANCH_BILLING created: BRANCHTYPE default 'B', BRANCHNAME 'BILLING' when BRANCHTYPE='B'")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'name in use' in error_msg:
            print("[DB INIT] Trigger TRG_AR_CUSTOMERBRANCH_BILLING already exists")
            return True
        print(f"[DB INIT WARNING] Could not create TRG_AR_CUSTOMERBRANCH_BILLING: {e}")
        return False
    finally:
        cur.close()


def _ensure_sl_qt_date_sync_trigger(conn):
    """Ensure POSTDATE and TAXDATE on SL_QT are always kept in sync with DOCDATE.

    The trigger fires BEFORE INSERT OR UPDATE so both INSERT (new quotation) and
    any subsequent UPDATE (e.g. status change) propagate the document date to the
    posting and tax date columns automatically.
    """
    cur = conn.cursor()
    try:
        try:
            cur.execute("DROP TRIGGER TRG_SL_QT_DATE_SYNC")
            conn.commit()
        except Exception:
            pass  # Trigger doesn't exist yet — that's fine

        trigger_sql = """
        CREATE TRIGGER TRG_SL_QT_DATE_SYNC FOR SL_QT
        ACTIVE BEFORE INSERT OR UPDATE POSITION 0
        AS
        BEGIN
          IF (NEW.DOCDATE IS NOT NULL) THEN
          BEGIN
            NEW.POSTDATE = NEW.DOCDATE;
            NEW.TAXDATE  = NEW.DOCDATE;
          END
        END
        """
        cur.execute(trigger_sql)
        conn.commit()
        print("[DB INIT] Trigger TRG_SL_QT_DATE_SYNC created: POSTDATE and TAXDATE will mirror DOCDATE on SL_QT")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'name in use' in error_msg:
            print("[DB INIT] Trigger TRG_SL_QT_DATE_SYNC already exists")
            return True
        print(f"[DB INIT WARNING] Could not create TRG_SL_QT_DATE_SYNC: {e}")
        return False
    finally:
        cur.close()


def _ensure_sl_qt_validity_sync_trigger(conn):
    """Ensure SL_QT.UDF_VALIDITY is always kept in sync with SL_QT.VALIDITY."""
    cur = conn.cursor()
    try:
        try:
            cur.execute("DROP TRIGGER TRG_SL_QT_VALIDITY_SYNC")
            conn.commit()
        except Exception:
            pass  # Trigger doesn't exist yet — that's fine

        trigger_sql = """
        CREATE TRIGGER TRG_SL_QT_VALIDITY_SYNC FOR SL_QT
        ACTIVE BEFORE INSERT OR UPDATE POSITION 1
        AS
        BEGIN
          IF (NEW.VALIDITY IS NOT NULL) THEN
            NEW.UDF_VALIDITY = NEW.VALIDITY;
        END
        """
        cur.execute(trigger_sql)
        conn.commit()
        print("[DB INIT] Trigger TRG_SL_QT_VALIDITY_SYNC created: UDF_VALIDITY will mirror VALIDITY on SL_QT")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'name in use' in error_msg:
            print("[DB INIT] Trigger TRG_SL_QT_VALIDITY_SYNC already exists")
            return True
        print(f"[DB INIT WARNING] Could not create TRG_SL_QT_VALIDITY_SYNC: {e}")
        return False
    finally:
        cur.close()


def _ensure_sl_qt_localdocamt_sync_trigger(conn):
    """Ensure SL_QT.LOCALDOCAMT is always kept in sync with DOCAMT * CURRENCYRATE."""
    cur = conn.cursor()
    try:
        try:
            cur.execute("DROP TRIGGER TRG_SL_QT_LOCALDOCAMT_SYNC")
            conn.commit()
        except Exception:
            pass  # Trigger doesn't exist yet — that's fine

        trigger_sql = """
        CREATE TRIGGER TRG_SL_QT_LOCALDOCAMT_SYNC FOR SL_QT
        ACTIVE BEFORE INSERT OR UPDATE POSITION 2
        AS
        BEGIN
          NEW.LOCALDOCAMT = NEW.DOCAMT * NEW.CURRENCYRATE;
        END
        """
        cur.execute(trigger_sql)
        conn.commit()
        print("[DB INIT] Trigger TRG_SL_QT_LOCALDOCAMT_SYNC created: LOCALDOCAMT will mirror DOCAMT * CURRENCYRATE on SL_QT")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'name in use' in error_msg:
            print("[DB INIT] Trigger TRG_SL_QT_LOCALDOCAMT_SYNC already exists")
            return True
        print(f"[DB INIT WARNING] Could not create TRG_SL_QT_LOCALDOCAMT_SYNC: {e}")
        return False
    finally:
        cur.close()


def _ensure_sl_qtdtl_sqty_sync_trigger(conn):
    """Ensure SL_QTDTL.SQTY is always kept in sync with QTY * RATE."""
    cur = conn.cursor()
    try:
        try:
            cur.execute("DROP TRIGGER TRG_SL_QTDTL_SQTY_SYNC")
            conn.commit()
        except Exception:
            pass  # Trigger doesn't exist yet — that's fine

        trigger_sql = """
        CREATE TRIGGER TRG_SL_QTDTL_SQTY_SYNC FOR SL_QTDTL
        ACTIVE BEFORE INSERT OR UPDATE POSITION 0
        AS
        BEGIN
          NEW.SQTY = COALESCE(NEW.QTY, 0) * COALESCE(NEW.RATE, 0);
        END
        """
        cur.execute(trigger_sql)
        conn.commit()
        print("[DB INIT] Trigger TRG_SL_QTDTL_SQTY_SYNC created: SQTY will mirror QTY * RATE on SL_QTDTL")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'name in use' in error_msg:
            print("[DB INIT] Trigger TRG_SL_QTDTL_SQTY_SYNC already exists")
            return True
        print(f"[DB INIT WARNING] Could not create TRG_SL_QTDTL_SQTY_SYNC: {e}")
        return False
    finally:
        cur.close()


def _ensure_sl_qtdtl_localamount_sync_trigger(conn):
    """Ensure SL_QTDTL.LOCALAMOUNT is always kept in sync with AMOUNT * SL_QT.CURRENCYRATE."""
    cur = conn.cursor()
    try:
        try:
            cur.execute("DROP TRIGGER TRG_SL_QTDTL_LOCALAMOUNT_SYNC")
            conn.commit()
        except Exception:
            pass  # Trigger doesn't exist yet — that's fine

        trigger_sql = """
        CREATE TRIGGER TRG_SL_QTDTL_LOCALAMOUNT_SYNC FOR SL_QTDTL
        ACTIVE BEFORE INSERT OR UPDATE POSITION 1
        AS
        DECLARE VARIABLE V_CURRENCYRATE DECIMAL(18, 8);
        BEGIN
          V_CURRENCYRATE = 1;

          SELECT FIRST 1 CURRENCYRATE
          FROM SL_QT
          WHERE DOCKEY = NEW.DOCKEY
          INTO :V_CURRENCYRATE;

          NEW.LOCALAMOUNT = COALESCE(NEW.AMOUNT, 0) * COALESCE(V_CURRENCYRATE, 1);
        END
        """
        cur.execute(trigger_sql)
        conn.commit()
        print("[DB INIT] Trigger TRG_SL_QTDTL_LOCALAMOUNT_SYNC created: LOCALAMOUNT will mirror AMOUNT * SL_QT.CURRENCYRATE on SL_QTDTL")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'name in use' in error_msg:
            print("[DB INIT] Trigger TRG_SL_QTDTL_LOCALAMOUNT_SYNC already exists")
            return True
        print(f"[DB INIT WARNING] Could not create TRG_SL_QTDTL_LOCALAMOUNT_SYNC: {e}")
        return False
    finally:
        cur.close()


def _ensure_pricing_priority_rule_table(conn):
    """Ensure PricingPriorityRule table exists for configurable price evaluation."""
    _execute_ddl(
        conn,
        """
        CREATE TABLE PricingPriorityRule (
            PricingPriorityRuleId INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            RuleCode VARCHAR(50) NOT NULL,
            RuleName VARCHAR(100) NOT NULL,
            PriorityNo INTEGER NOT NULL,
            IsEnabled SMALLINT DEFAULT 1 NOT NULL,
            AddDate TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
            EditDate TIMESTAMP,
            CONSTRAINT UQ_PricingPriorityRule_RuleCode UNIQUE (RuleCode),
            CONSTRAINT CK_PricingPriorityRule_IsEnabled CHECK (IsEnabled IN (0, 1))
        )
        """,
        success_message='[DB INIT] PricingPriorityRule table created.',
        ignore_if_contains=['already exists', 'name in use']
    )

    _execute_ddl(
        conn,
        'CREATE ASC INDEX IDX_PricingPriorityRule_PriorityNo ON PricingPriorityRule (PriorityNo)',
        success_message='[DB INIT] PricingPriorityRule priority index created.',
        ignore_if_contains=['already exists', 'name in use']
    )


def _seed_pricing_priority_rules(conn):
    """Insert missing default pricing priority rules without overwriting saved admin order."""
    cur = conn.cursor()
    inserted = 0
    try:
        for rule_code, rule_name, priority_no, is_enabled in PRICING_PRIORITY_RULE_DEFAULTS:
            cur.execute(
                'SELECT PricingPriorityRuleId FROM PricingPriorityRule WHERE RuleCode = ?',
                (rule_code,)
            )
            if cur.fetchone():
                continue

            cur.execute(
                '''
                INSERT INTO PricingPriorityRule (RuleCode, RuleName, PriorityNo, IsEnabled, AddDate)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''',
                (rule_code, rule_name, priority_no, is_enabled)
            )
            inserted += 1

        conn.commit()
        if inserted:
            print(f'[DB INIT] Seeded {inserted} PricingPriorityRule rows.')
        else:
            print('[DB INIT] PricingPriorityRule seed data already present.')
    except Exception as e:
        conn.rollback()
        print(f'[DB INIT WARNING] Could not seed PricingPriorityRule: {e}')
    finally:
        cur.close()


def _ensure_sl_qt_draft_tables(conn):
    """Ensure draft quotation header/detail tables exist for pre-submission storage."""
    _execute_ddl(
        conn,
        """
        CREATE TABLE SL_QTDRAFT (
            DOCKEY INTEGER NOT NULL,
            DOCNO VARCHAR(160) NOT NULL,
            DOCNOEX VARCHAR(160),
            DOCDATE DATE,
            POSTDATE DATE,
            TAXDATE DATE,
            CODE VARCHAR(40),
            COMPANYNAME VARCHAR(400),
            ADDRESS1 VARCHAR(240),
            ADDRESS2 VARCHAR(240),
            ADDRESS3 VARCHAR(240),
            ADDRESS4 VARCHAR(240),
            POSTCODE VARCHAR(40),
            CITY VARCHAR(200),
            STATE VARCHAR(200),
            COUNTRY VARCHAR(8),
            PHONE1 VARCHAR(800),
            MOBILE VARCHAR(800),
            FAX1 VARCHAR(800),
            ATTENTION VARCHAR(280),
            AREA VARCHAR(40),
            AGENT VARCHAR(40),
            PROJECT VARCHAR(80),
            TERMS VARCHAR(40),
            CURRENCYCODE VARCHAR(24),
            CURRENCYRATE DECIMAL(18,8),
            SHIPPER VARCHAR(120) NOT NULL,
            DESCRIPTION VARCHAR(1200),
            CANCELLED CHAR(1),
            STATUS INTEGER,
            DOCAMT DECIMAL(18,2),
            LOCALDOCAMT DECIMAL(18,2),
            VALIDITY VARCHAR(1200),
            DELIVERYTERM VARCHAR(1200),
            CC VARCHAR(1200),
            DOCREF1 VARCHAR(160),
            DOCREF2 VARCHAR(160),
            DOCREF3 VARCHAR(160),
            DOCREF4 VARCHAR(160),
            BRANCHNAME VARCHAR(400),
            DADDRESS1 VARCHAR(240),
            DADDRESS2 VARCHAR(240),
            DADDRESS3 VARCHAR(240),
            DADDRESS4 VARCHAR(240),
            DPOSTCODE VARCHAR(40),
            DCITY VARCHAR(200),
            DSTATE VARCHAR(200),
            DCOUNTRY VARCHAR(8),
            DATTENTION VARCHAR(280),
            DPHONE1 VARCHAR(800),
            DMOBILE VARCHAR(800),
            DFAX1 VARCHAR(800),
            TAXEXEMPTNO VARCHAR(200),
            SALESTAXNO VARCHAR(100),
            SERVICETAXNO VARCHAR(100),
            TIN VARCHAR(56),
            IDTYPE SMALLINT,
            IDNO VARCHAR(80),
            TOURISMNO VARCHAR(68),
            SIC VARCHAR(40),
            INCOTERMS VARCHAR(12),
            SUBMISSIONTYPE INTEGER,
            BUSINESSUNIT VARCHAR(40),
            ATTACHMENTS BLOB SUB_TYPE TEXT,
            NOTE BLOB SUB_TYPE TEXT,
            APPROVESTATE BLOB SUB_TYPE TEXT,
            TRANSFERABLE CHAR(1),
            UPDATECOUNT INTEGER,
            PRINTCOUNT INTEGER,
            LASTMODIFIED DECIMAL(18,0),
            UDF_STATUS VARCHAR(60),
            UDF_VALIDITY DATE,
            CONSTRAINT PK_SL_QTDRAFT PRIMARY KEY (DOCKEY)
        )
        """,
        success_message='[DB INIT] SL_QTDRAFT table created.',
        ignore_if_contains=['already exists', 'name in use']
    )

    _execute_ddl(
        conn,
        """
        CREATE TABLE SL_QTDTLDRAFT (
            DTLKEY INTEGER NOT NULL,
            DOCKEY INTEGER NOT NULL,
            SEQ INTEGER,
            STYLEID VARCHAR(20),
            NUMBER VARCHAR(20),
            ITEMCODE VARCHAR(120),
            LOCATION VARCHAR(80),
            BATCH VARCHAR(120),
            PROJECT VARCHAR(80),
            DESCRIPTION VARCHAR(800),
            DESCRIPTION2 VARCHAR(800),
            DESCRIPTION3 BLOB SUB_TYPE TEXT,
            PERMITNO VARCHAR(80),
            QTY DECIMAL(18,4),
            UOM VARCHAR(40),
            RATE DECIMAL(18,4),
            SQTY DECIMAL(18,4),
            SUOMQTY DECIMAL(18,4),
            UNITPRICE DECIMAL(18,8),
            DELIVERYDATE DATE,
            DISC VARCHAR(80),
            TAX VARCHAR(40),
            TARIFF VARCHAR(80),
            TAXEXEMPTIONREASON VARCHAR(1200),
            IRBM_CLASSIFICATION VARCHAR(3),
            TAXRATE VARCHAR(80),
            TAXAMT DECIMAL(18,2),
            LOCALTAXAMT DECIMAL(18,2),
            EXEMPTED_TAXRATE VARCHAR(80),
            EXEMPTED_TAXAMT DECIMAL(18,2),
            TAXINCLUSIVE CHAR(1),
            AMOUNT DECIMAL(18,2),
            LOCALAMOUNT DECIMAL(18,2),
            PRINTABLE CHAR(1),
            TRANSFERABLE CHAR(1),
            REMARK1 VARCHAR(800),
            REMARK2 VARCHAR(800),
            INITIALPURCHASECOST DECIMAL(18,2),
            UDF_STATUS VARCHAR(60),
            UDF_STDPRICE DECIMAL(18,4),
            CONSTRAINT PK_SL_QTDTLDRAFT PRIMARY KEY (DTLKEY),
            CONSTRAINT FK_SL_QTDTLDRAFT_QT FOREIGN KEY (DOCKEY) REFERENCES SL_QTDRAFT(DOCKEY)
        )
        """,
        success_message='[DB INIT] SL_QTDTLDRAFT table created.',
        ignore_if_contains=['already exists', 'name in use']
    )

    _execute_ddl(
        conn,
        'CREATE ASC INDEX IDX_SL_QTDTLDRAFT_DOCKEY ON SL_QTDTLDRAFT (DOCKEY)',
        success_message='[DB INIT] SL_QTDTLDRAFT DOCKEY index created.',
        ignore_if_contains=['already exists', 'name in use']
    )


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

        # Ensure dedicated draft quotation tables exist.
        _ensure_sl_qt_draft_tables(conn)

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

        # Keep AR_CUSTOMER.IDNO synchronized with BRN2 for inserts/updates
        _ensure_ar_customer_idno_from_brn2_trigger(conn)

        # Default/enforce branch type/name for AR_CUSTOMERBRANCH
        _ensure_ar_customerbranch_branchtype_branchname_trigger(conn)

        # Keep SL_QT.POSTDATE and TAXDATE in sync with DOCDATE
        _ensure_sl_qt_date_sync_trigger(conn)

        # Keep SL_QT.UDF_VALIDITY in sync with VALIDITY
        _ensure_sl_qt_validity_sync_trigger(conn)

        # Keep SL_QT.LOCALDOCAMT in sync with DOCAMT * CURRENCYRATE
        _ensure_sl_qt_localdocamt_sync_trigger(conn)

        # Keep SL_QTDTL.SQTY in sync with QTY * RATE
        _ensure_sl_qtdtl_sqty_sync_trigger(conn)

        # Keep SL_QTDTL.LOCALAMOUNT in sync with AMOUNT * SL_QT.CURRENCYRATE
        _ensure_sl_qtdtl_localamount_sync_trigger(conn)

        # Ensure pricing priority rule settings table exists and is seeded
        _ensure_pricing_priority_rule_table(conn)
        _seed_pricing_priority_rules(conn)

    except Exception as e:
        print(f"[DB INIT ERROR] {e}")
    finally:
        if conn:
            conn.close()
