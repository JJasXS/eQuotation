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

        # Add TERMS column if it doesn’t exist
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


def _ensure_sl_qt_remarks_column(conn):
    """Ensure SL_QT table has a REMARKS column for manual quotation remarks."""
    cur = conn.cursor()
    try:
        cur.execute(
            '''
            SELECT f.RDB$FIELD_NAME
            FROM RDB$RELATION_FIELDS f
            WHERE f.RDB$RELATION_NAME = 'SL_QT' AND f.RDB$FIELD_NAME = 'REMARKS'
            '''
        )
        result = cur.fetchone()
        if result:
            print("[DB INIT] REMARKS column already exists in SL_QT")
            return True

        conn.commit()
        cur.execute('ALTER TABLE SL_QT ADD REMARKS VARCHAR(1000)')
        conn.commit()
        print("[DB INIT] REMARKS column added to SL_QT")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'duplicate' in error_msg:
            print("[DB INIT] REMARKS column already exists in SL_QT")
            return True
        print(f"[DB INIT WARNING] Could not add REMARKS to SL_QT: {e}")
        return False
    finally:
        cur.close()


def _ensure_sl_qtdtl_remarks_column(conn):
    """Ensure SL_QTDTL table has a REMARKS column for item-level remarks."""
    cur = conn.cursor()
    try:
        cur.execute(
            '''
            SELECT f.RDB$FIELD_NAME
            FROM RDB$RELATION_FIELDS f
            WHERE f.RDB$RELATION_NAME = 'SL_QTDTL' AND f.RDB$FIELD_NAME = 'REMARKS'
            '''
        )
        result = cur.fetchone()
        if result:
            print("[DB INIT] REMARKS column already exists in SL_QTDTL")
            return True

        conn.commit()
        cur.execute('ALTER TABLE SL_QTDTL ADD REMARKS VARCHAR(1000)')
        conn.commit()
        print("[DB INIT] REMARKS column added to SL_QTDTL")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'duplicate' in error_msg:
            print("[DB INIT] REMARKS column already exists in SL_QTDTL")
            return True
        print(f"[DB INIT WARNING] Could not add REMARKS to SL_QTDTL: {e}")
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


def _ensure_st_item_udf_uom_column(conn):
    """Ensure ST_ITEM table has UDF_UOM column for quotation item UOM lookups."""
    cur = conn.cursor()
    try:
        cur.execute(
            '''
            SELECT f.RDB$FIELD_NAME
            FROM RDB$RELATION_FIELDS f
            WHERE f.RDB$RELATION_NAME = 'ST_ITEM' AND f.RDB$FIELD_NAME = 'UDF_UOM'
            '''
        )
        result = cur.fetchone()
        if result:
            print("[DB INIT] UDF_UOM column already exists in ST_ITEM")
            return True

        conn.commit()
        cur.execute('ALTER TABLE ST_ITEM ADD UDF_UOM VARCHAR(40)')
        conn.commit()
        print("[DB INIT] UDF_UOM column added to ST_ITEM")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'duplicate' in error_msg:
            print("[DB INIT] UDF_UOM column already exists in ST_ITEM")
            return True
        print(f"[DB INIT WARNING] Could not add UDF_UOM to ST_ITEM: {e}")
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


def _ensure_sl_qt_address_sync_trigger(conn):
    """Ensure SL_QT billing address fields are always kept in sync with delivery address fields."""
    cur = conn.cursor()
    try:
        try:
            cur.execute("DROP TRIGGER TR_SL_QT_SET_ADDRESS")
            conn.commit()
        except Exception:
            pass  # Trigger doesn't exist yet — that's fine

        trigger_sql = """
        CREATE TRIGGER TR_SL_QT_SET_ADDRESS FOR SL_QT
        ACTIVE BEFORE INSERT OR UPDATE POSITION 0
        AS
        BEGIN
          -- Sync when either side changes; use OLD values on UPDATE to know which field was modified.
          -- On INSERT, apply whichever value exists (billing or delivery), with billing as source if both non-empty.

          IF (INSERTING OR (NEW.ADDRESS1 IS DISTINCT FROM OLD.ADDRESS1)) THEN
          BEGIN
            IF (NEW.ADDRESS1 IS NOT NULL AND TRIM(NEW.ADDRESS1) <> '') THEN
              NEW.DADDRESS1 = NEW.ADDRESS1;
            ELSE
              NEW.ADDRESS1 = NEW.DADDRESS1;
          END
          ELSE IF (NEW.DADDRESS1 IS DISTINCT FROM OLD.DADDRESS1) THEN
            NEW.ADDRESS1 = NEW.DADDRESS1;

          IF (INSERTING OR (NEW.ADDRESS2 IS DISTINCT FROM OLD.ADDRESS2)) THEN
          BEGIN
            IF (NEW.ADDRESS2 IS NOT NULL AND TRIM(NEW.ADDRESS2) <> '') THEN
              NEW.DADDRESS2 = NEW.ADDRESS2;
            ELSE
              NEW.ADDRESS2 = NEW.DADDRESS2;
          END
          ELSE IF (NEW.DADDRESS2 IS DISTINCT FROM OLD.DADDRESS2) THEN
            NEW.ADDRESS2 = NEW.DADDRESS2;

          IF (INSERTING OR (NEW.ADDRESS3 IS DISTINCT FROM OLD.ADDRESS3)) THEN
          BEGIN
            IF (NEW.ADDRESS3 IS NOT NULL AND TRIM(NEW.ADDRESS3) <> '') THEN
              NEW.DADDRESS3 = NEW.ADDRESS3;
            ELSE
              NEW.ADDRESS3 = NEW.DADDRESS3;
          END
          ELSE IF (NEW.DADDRESS3 IS DISTINCT FROM OLD.DADDRESS3) THEN
            NEW.ADDRESS3 = NEW.DADDRESS3;

          IF (INSERTING OR (NEW.ADDRESS4 IS DISTINCT FROM OLD.ADDRESS4)) THEN
          BEGIN
            IF (NEW.ADDRESS4 IS NOT NULL AND TRIM(NEW.ADDRESS4) <> '') THEN
              NEW.DADDRESS4 = NEW.ADDRESS4;
            ELSE
              NEW.ADDRESS4 = NEW.DADDRESS4;
          END
          ELSE IF (NEW.DADDRESS4 IS DISTINCT FROM OLD.DADDRESS4) THEN
            NEW.ADDRESS4 = NEW.DADDRESS4;

          IF (INSERTING OR (NEW.POSTCODE IS DISTINCT FROM OLD.POSTCODE)) THEN
          BEGIN
            IF (NEW.POSTCODE IS NOT NULL AND TRIM(NEW.POSTCODE) <> '') THEN
              NEW.DPOSTCODE = NEW.POSTCODE;
            ELSE
              NEW.POSTCODE = NEW.DPOSTCODE;
          END
          ELSE IF (NEW.DPOSTCODE IS DISTINCT FROM OLD.DPOSTCODE) THEN
            NEW.POSTCODE = NEW.DPOSTCODE;

          IF (INSERTING OR (NEW.CITY IS DISTINCT FROM OLD.CITY)) THEN
          BEGIN
            IF (NEW.CITY IS NOT NULL AND TRIM(NEW.CITY) <> '') THEN
              NEW.DCITY = NEW.CITY;
            ELSE
              NEW.CITY = NEW.DCITY;
          END
          ELSE IF (NEW.DCITY IS DISTINCT FROM OLD.DCITY) THEN
            NEW.CITY = NEW.DCITY;

          IF (INSERTING OR (NEW.STATE IS DISTINCT FROM OLD.STATE)) THEN
          BEGIN
            IF (NEW.STATE IS NOT NULL AND TRIM(NEW.STATE) <> '') THEN
              NEW.DSTATE = NEW.STATE;
            ELSE
              NEW.STATE = NEW.DSTATE;
          END
          ELSE IF (NEW.DSTATE IS DISTINCT FROM OLD.DSTATE) THEN
            NEW.STATE = NEW.DSTATE;

          IF (INSERTING OR (NEW.COUNTRY IS DISTINCT FROM OLD.COUNTRY)) THEN
          BEGIN
            IF (NEW.COUNTRY IS NOT NULL AND TRIM(NEW.COUNTRY) <> '') THEN
              NEW.DCOUNTRY = NEW.COUNTRY;
            ELSE
              NEW.COUNTRY = NEW.DCOUNTRY;
          END
          ELSE IF (NEW.DCOUNTRY IS DISTINCT FROM OLD.DCOUNTRY) THEN
            NEW.COUNTRY = NEW.DCOUNTRY;

          IF (INSERTING OR (NEW.PHONE1 IS DISTINCT FROM OLD.PHONE1)) THEN
          BEGIN
            IF (NEW.PHONE1 IS NOT NULL AND TRIM(NEW.PHONE1) <> '') THEN
              NEW.DPHONE1 = NEW.PHONE1;
            ELSE
              NEW.PHONE1 = NEW.DPHONE1;
          END
          ELSE IF (NEW.DPHONE1 IS DISTINCT FROM OLD.DPHONE1) THEN
            NEW.PHONE1 = NEW.DPHONE1;

          IF (INSERTING OR (NEW.MOBILE IS DISTINCT FROM OLD.MOBILE)) THEN
          BEGIN
            IF (NEW.MOBILE IS NOT NULL AND TRIM(NEW.MOBILE) <> '') THEN
              NEW.DMOBILE = NEW.MOBILE;
            ELSE
              NEW.MOBILE = NEW.DMOBILE;
          END
          ELSE IF (NEW.DMOBILE IS DISTINCT FROM OLD.DMOBILE) THEN
            NEW.MOBILE = NEW.DMOBILE;

          IF (INSERTING OR (NEW.FAX1 IS DISTINCT FROM OLD.FAX1)) THEN
          BEGIN
            IF (NEW.FAX1 IS NOT NULL AND TRIM(NEW.FAX1) <> '') THEN
              NEW.DFAX1 = NEW.FAX1;
            ELSE
              NEW.FAX1 = NEW.DFAX1;
          END
          ELSE IF (NEW.DFAX1 IS DISTINCT FROM OLD.DFAX1) THEN
            NEW.FAX1 = NEW.DFAX1;

          IF (INSERTING OR (NEW.ATTENTION IS DISTINCT FROM OLD.ATTENTION)) THEN
          BEGIN
            IF (NEW.ATTENTION IS NOT NULL AND TRIM(NEW.ATTENTION) <> '') THEN
              NEW.DATTENTION = NEW.ATTENTION;
            ELSE
              NEW.ATTENTION = NEW.DATTENTION;
          END
          ELSE IF (NEW.DATTENTION IS DISTINCT FROM OLD.DATTENTION) THEN
            NEW.ATTENTION = NEW.DATTENTION;
        END
        """
        cur.execute(trigger_sql)
        conn.commit()
        print("[DB INIT] Trigger TR_SL_QT_SET_ADDRESS created: billing address fields will mirror delivery address fields on SL_QT")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'name in use' in error_msg:
            print("[DB INIT] Trigger TR_SL_QT_SET_ADDRESS already exists")
            return True
        print(f"[DB INIT WARNING] Could not create TR_SL_QT_SET_ADDRESS: {e}")
        return False
    finally:
        cur.close()


def _ensure_sl_qt_cancelled_status_sync_trigger(conn):
    """Ensure SL_QT.STATUS always follows SL_QT.CANCELLED.

    Rules:
    - CANCELLED = TRUE  -> STATUS = -10
    - CANCELLED = FALSE -> STATUS = 0
    """
    cur = conn.cursor()
    try:
        try:
            cur.execute("DROP TRIGGER TRG_SL_QT_CANCELLED_STATUS_SYNC")
            conn.commit()
        except Exception:
            pass  # Trigger doesn't exist yet — that's fine

        trigger_sql = """
        CREATE TRIGGER TRG_SL_QT_CANCELLED_STATUS_SYNC FOR SL_QT
        ACTIVE BEFORE INSERT OR UPDATE POSITION 3
        AS
        BEGIN
          IF (NEW.CANCELLED = TRUE) THEN
            NEW.STATUS = -10;
          ELSE
            NEW.STATUS = 0;
        END
        """
        cur.execute(trigger_sql)
        conn.commit()
        print("[DB INIT] Trigger TRG_SL_QT_CANCELLED_STATUS_SYNC created: STATUS=-10 when CANCELLED=TRUE, otherwise STATUS=0")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'name in use' in error_msg:
            print("[DB INIT] Trigger TRG_SL_QT_CANCELLED_STATUS_SYNC already exists")
            return True
        print(f"[DB INIT WARNING] Could not create TRG_SL_QT_CANCELLED_STATUS_SYNC: {e}")
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


def _get_relation_field_names(conn, relation_name):
    """Return existing field names for a Firebird table/relation in uppercase."""
    cur = conn.cursor()
    try:
        cur.execute(
            '''
            SELECT TRIM(f.RDB$FIELD_NAME)
            FROM RDB$RELATION_FIELDS f
            WHERE f.RDB$RELATION_NAME = ?
            ''',
            (relation_name.upper(),)
        )
        return {str(row[0]).strip().upper() for row in cur.fetchall() if row and row[0]}
    except Exception as e:
        print(f"[DB INIT WARNING] Could not inspect fields for {relation_name}: {e}")
        return set()
    finally:
        cur.close()


def _ensure_st_tr_udf_suomqty_column(conn):
    """Ensure ST_TR.UDF_SUOMQTY exists (parallel to SQTY; same NUMERIC(18,4) as common SQTY columns)."""
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT 1
            FROM RDB$RELATIONS
            WHERE RDB$RELATION_NAME = 'ST_TR'
              AND COALESCE(RDB$SYSTEM_FLAG, 0) = 0
            """
        )
        if not cur.fetchone():
            print("[DB INIT] ST_TR not found; UDF_SUOMQTY ensure skipped")
            return False

        cur.execute(
            """
            SELECT f.RDB$FIELD_NAME
            FROM RDB$RELATION_FIELDS f
            WHERE f.RDB$RELATION_NAME = 'ST_TR' AND f.RDB$FIELD_NAME = 'UDF_SUOMQTY'
            """
        )
        if cur.fetchone():
            print("[DB INIT] UDF_SUOMQTY column already exists in ST_TR")
            return True

        conn.commit()
        cur.execute("ALTER TABLE ST_TR ADD UDF_SUOMQTY NUMERIC(18, 4)")
        conn.commit()
        print("[DB INIT] UDF_SUOMQTY column added to ST_TR")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg or "duplicate" in error_msg:
            print("[DB INIT] UDF_SUOMQTY column already exists in ST_TR")
            return True
        print(f"[DB INIT WARNING] Could not add UDF_SUOMQTY to ST_TR: {e}")
        return False
    finally:
        cur.close()


def _relation_exists(conn, relation_name):
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT 1
            FROM RDB$RELATIONS
            WHERE RDB$RELATION_NAME = ?
              AND COALESCE(RDB$SYSTEM_FLAG, 0) = 0
            """,
            (relation_name.upper(),)
        )
        return cur.fetchone() is not None
    except Exception:
        return False
    finally:
        cur.close()


def _st_tr_direction_column(st_tr_fields):
    """Use ST_TR.SQTY when available; SQL Accounting DBs commonly only have ST_TR.QTY."""
    if 'SQTY' in st_tr_fields:
        return 'SQTY'
    if 'QTY' in st_tr_fields:
        return 'QTY'
    return ''


def _stock_source_raw_expr(fields, alias='D'):
    parts = []
    if 'SUOMQTY' in fields:
        parts.append(f'{alias}.SUOMQTY')
    if 'SQTY' in fields:
        parts.append(f'{alias}.SQTY')
    if 'QTY' in fields:
        parts.append(f'{alias}.QTY')
    if not parts:
        return ''
    return 'COALESCE(' + ', '.join(parts + ['0']) + ')'


def _st_tr_source_specs(conn):
    """Source tables used to populate ST_TR.UDF_SUOMQTY from the posted document row."""
    candidates = [
        ('GR', 'PH_GRDTL', 'DETAIL'),
        ('PI', 'PH_PIDTL', 'DETAIL'),
        ('RC', 'ST_RCDTL', 'DETAIL'),
        ('RC', 'ST_RCDRL', 'DETAIL'),
        ('DO', 'SL_DODTL', 'DETAIL'),
        ('IV', 'SL_IVDTL', 'DETAIL'),
        ('IS', 'ST_ISDTL', 'DETAIL'),
        ('AS', 'ST_ASDTL', 'DETAIL'),
        ('AS', 'ST_AS', 'HEADER'),
        ('DS', 'ST_DSDTL', 'DETAIL'),
        ('AJ', 'ST_AJDTL', 'DETAIL'),
        ('XF', 'ST_XFDTL', 'DETAIL'),
    ]

    specs = []
    seen = set()
    for doctype, table_name, row_kind in candidates:
        key = (doctype, table_name)
        if key in seen or not _relation_exists(conn, table_name):
            continue
        seen.add(key)
        fields = _get_relation_field_names(conn, table_name)
        expr = _stock_source_raw_expr(fields, 'D')
        if not expr or 'DOCKEY' not in fields:
            continue
        if row_kind == 'DETAIL' and 'DTLKEY' not in fields:
            continue
        specs.append({
            'doctype': doctype,
            'table': table_name,
            'kind': row_kind,
            'expr': expr,
            'fields': fields,
        })
    return specs


def _st_tr_source_join_condition(spec, st_alias='S', src_alias='D'):
    if spec['kind'] == 'HEADER':
        return (
            f"{src_alias}.DOCKEY = {st_alias}.DOCKEY "
            f"AND COALESCE({st_alias}.DTLKEY, 0) = 0"
        )
    return f"{src_alias}.DOCKEY = {st_alias}.DOCKEY AND {src_alias}.DTLKEY = {st_alias}.DTLKEY"


def _backfill_st_tr_udf_suomqty(conn):
    """Backfill ST_TR.UDF_SUOMQTY from source SUOMQTY/SQTY using ST_TR direction."""
    st_fields = _get_relation_field_names(conn, 'ST_TR')
    if 'UDF_SUOMQTY' not in st_fields:
        print("[DB INIT WARNING] ST_TR.UDF_SUOMQTY is missing; backfill skipped")
        return False

    direction_col = _st_tr_direction_column(st_fields)
    if not direction_col:
        print("[DB INIT WARNING] ST_TR has no SQTY/QTY direction column; UDF_SUOMQTY backfill skipped")
        return False

    specs = _st_tr_source_specs(conn)
    if not specs:
        print("[DB INIT WARNING] No source tables found for ST_TR.UDF_SUOMQTY backfill")
        return False

    cur = conn.cursor()
    total_updated = 0
    try:
        for spec in specs:
            join_condition = _st_tr_source_join_condition(spec)
            raw_subquery = (
                f"(SELECT FIRST 1 {spec['expr']} "
                f"FROM {spec['table']} D "
                f"WHERE {join_condition})"
            )
            cur.execute(
                f"""
                UPDATE ST_TR S
                SET UDF_SUOMQTY =
                    CASE
                        WHEN COALESCE(S.{direction_col}, 0) < 0 THEN -ABS({raw_subquery})
                        ELSE ABS({raw_subquery})
                    END
                WHERE S.DOCTYPE = ?
                  AND S.UDF_SUOMQTY IS NULL
                  AND EXISTS (
                      SELECT 1
                      FROM {spec['table']} D
                      WHERE {join_condition}
                  )
                """,
                (spec['doctype'],)
            )
            total_updated += int(cur.rowcount or 0)
        conn.commit()
        print(f"[DB INIT] Backfilled ST_TR.UDF_SUOMQTY for {total_updated} rows")
        return True
    except Exception as e:
        conn.rollback()
        print(f"[DB INIT WARNING] Could not backfill ST_TR.UDF_SUOMQTY: {e}")
        return False
    finally:
        cur.close()


def _ensure_st_tr_udf_suomqty_sync_trigger(conn):
    """Populate ST_TR.UDF_SUOMQTY for future stock postings."""
    st_fields = _get_relation_field_names(conn, 'ST_TR')
    if 'UDF_SUOMQTY' not in st_fields:
        print("[DB INIT WARNING] ST_TR.UDF_SUOMQTY is missing; trigger skipped")
        return False

    direction_col = _st_tr_direction_column(st_fields)
    if not direction_col:
        print("[DB INIT WARNING] ST_TR has no SQTY/QTY direction column; trigger skipped")
        return False

    specs = _st_tr_source_specs(conn)
    if not specs:
        print("[DB INIT WARNING] No source tables found for ST_TR.UDF_SUOMQTY trigger")
        return False

    blocks = []
    for spec in specs:
        if spec['kind'] == 'HEADER':
            condition = f"NEW.DOCTYPE = '{spec['doctype']}' AND COALESCE(NEW.DTLKEY, 0) = 0"
            where = "D.DOCKEY = NEW.DOCKEY"
        else:
            condition = f"NEW.DOCTYPE = '{spec['doctype']}'"
            where = "D.DOCKEY = NEW.DOCKEY AND D.DTLKEY = NEW.DTLKEY"
        blocks.append(
            f"""
          IF ({condition}) THEN
            SELECT FIRST 1 {spec['expr']}
            FROM {spec['table']} D
            WHERE {where}
            INTO :V_RAW;
            """
        )

    trigger_sql = f"""
        CREATE TRIGGER TRG_ST_TR_UDF_SUOMQTY_SYNC FOR ST_TR
        ACTIVE BEFORE INSERT OR UPDATE POSITION 0
        AS
        DECLARE VARIABLE V_RAW NUMERIC(18, 4);
        BEGIN
          V_RAW = NULL;
          {"".join(blocks)}

          IF (V_RAW IS NULL) THEN
            V_RAW = 0;

          IF (COALESCE(NEW.{direction_col}, 0) < 0) THEN
            NEW.UDF_SUOMQTY = -ABS(V_RAW);
          ELSE
            NEW.UDF_SUOMQTY = ABS(V_RAW);
        END
    """

    cur = conn.cursor()
    try:
        try:
            cur.execute("DROP TRIGGER TRG_ST_TR_UDF_SUOMQTY_SYNC")
            conn.commit()
        except Exception:
            pass

        cur.execute(trigger_sql)
        conn.commit()
        print(
            "[DB INIT] Trigger TRG_ST_TR_UDF_SUOMQTY_SYNC created: "
            f"UDF_SUOMQTY follows ST_TR.{direction_col} sign"
        )
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'name in use' in error_msg:
            print("[DB INIT] Trigger TRG_ST_TR_UDF_SUOMQTY_SYNC already exists")
            return True
        print(f"[DB INIT WARNING] Could not create TRG_ST_TR_UDF_SUOMQTY_SYNC: {e}")
        return False
    finally:
        cur.close()


def _ensure_st_xtrans_suomqty_column(conn):
    """Ensure ST_XTRANS table has SUOMQTY column for stock/UOM quantity tracking."""
    cur = conn.cursor()
    try:
        cur.execute(
            '''
            SELECT f.RDB$FIELD_NAME
            FROM RDB$RELATION_FIELDS f
            WHERE f.RDB$RELATION_NAME = 'ST_XTRANS' AND f.RDB$FIELD_NAME = 'SUOMQTY'
            '''
        )
        result = cur.fetchone()
        if result:
            print("[DB INIT] SUOMQTY column already exists in ST_XTRANS")
            return True

        conn.commit()
        cur.execute('ALTER TABLE ST_XTRANS ADD SUOMQTY DECIMAL(18,4)')
        conn.commit()
        print("[DB INIT] SUOMQTY column added to ST_XTRANS")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'duplicate' in error_msg:
            print("[DB INIT] SUOMQTY column already exists in ST_XTRANS")
            return True
        print(f"[DB INIT WARNING] Could not add SUOMQTY to ST_XTRANS: {e}")
        return False
    finally:
        cur.close()


def _backfill_st_xtrans_suomqty(conn):
    """
    Backfill missing ST_XTRANS.SUOMQTY values to 0.

    SUOMQTY is a distinct quantity and must not be inferred from SQTY/QTY.
    Missing true SUOM quantity is stored as 0.
    """
    fields = _get_relation_field_names(conn, 'ST_XTRANS')
    if 'SUOMQTY' not in fields:
        print("[DB INIT WARNING] ST_XTRANS.SUOMQTY is missing; zero backfill skipped")
        return False

    cur = conn.cursor()
    try:
        cur.execute('''
            UPDATE ST_XTRANS
            SET SUOMQTY = 0
            WHERE SUOMQTY IS NULL
        ''')
        conn.commit()
        print("[DB INIT] Backfilled ST_XTRANS.SUOMQTY NULL values to 0")
        return True
    except Exception as e:
        conn.rollback()
        print(f"[DB INIT WARNING] Could not zero-fill ST_XTRANS.SUOMQTY: {e}")
        return False
    finally:
        cur.close()


def _backfill_st_xtrans_suomqty_from_st_tr_udf(conn):
    """
    Overlay ST_XTRANS.SUOMQTY with aggregated ST_TR.UDF_SUOMQTY for the *to* document line:

        ST_XTRANS.TODOCTYPE = ST_TR.DOCTYPE
        ST_XTRANS.TODOCKEY = ST_TR.DOCKEY
        ST_XTRANS.TODTLKEY  = ST_TR.DTLKEY

    Multiple ST_TR rows for the same line are summed. Rows with no matching ST_TR are left unchanged.
    """
    x_fields = _get_relation_field_names(conn, "ST_XTRANS")
    s_fields = _get_relation_field_names(conn, "ST_TR")
    need_x = {"SUOMQTY", "TODOCTYPE", "TODOCKEY", "TODTLKEY"}
    need_s = {"UDF_SUOMQTY", "DOCTYPE", "DOCKEY", "DTLKEY"}
    if not need_x.issubset(x_fields):
        print(
            "[DB INIT WARNING] ST_XTRANS missing SUOMQTY or TODOCTYPE/TODOCKEY/TODTLKEY; "
            "ST_TR UDF → ST_XTRANS.SUOMQTY backfill skipped"
        )
        return False
    if not need_s.issubset(s_fields):
        print(
            "[DB INIT WARNING] ST_TR missing UDF_SUOMQTY or DOCTYPE/DOCKEY/DTLKEY; "
            "ST_TR UDF → ST_XTRANS.SUOMQTY backfill skipped"
        )
        return False

    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE ST_XTRANS X
            SET SUOMQTY = COALESCE((
                SELECT CAST(SUM(CAST(COALESCE(S.UDF_SUOMQTY, 0) AS DOUBLE PRECISION)) AS DOUBLE PRECISION)
                FROM ST_TR S
                WHERE TRIM(UPPER(COALESCE(S.DOCTYPE, ''))) = TRIM(UPPER(COALESCE(X.TODOCTYPE, '')))
                  AND S.DOCKEY = X.TODOCKEY
                  AND S.DTLKEY = X.TODTLKEY
            ), 0)
            WHERE X.TODOCKEY IS NOT NULL
              AND X.TODTLKEY IS NOT NULL
              AND TRIM(COALESCE(X.TODOCTYPE, '')) <> ''
              AND EXISTS (
                  SELECT 1
                  FROM ST_TR S2
                  WHERE TRIM(UPPER(COALESCE(S2.DOCTYPE, ''))) = TRIM(UPPER(COALESCE(X.TODOCTYPE, '')))
                    AND S2.DOCKEY = X.TODOCKEY
                    AND S2.DTLKEY = X.TODTLKEY
              )
            """
        )
        rc = cur.rowcount
        conn.commit()
        try:
            rc_n = int(rc) if rc is not None and int(rc) >= 0 else None
        except Exception:
            rc_n = None
        if rc_n is not None:
            print(f"[DB INIT] ST_XTRANS.SUOMQTY set from ST_TR.UDF_SUOMQTY ({rc_n} row(s))")
        else:
            print("[DB INIT] ST_XTRANS.SUOMQTY set from ST_TR.UDF_SUOMQTY (complete)")
        return True
    except Exception as e:
        conn.rollback()
        print(f"[DB INIT WARNING] Could not set ST_XTRANS.SUOMQTY from ST_TR.UDF_SUOMQTY: {e}")
        return False
    finally:
        cur.close()


def sync_st_xtrans_suomqty_from_st_tr_udf(conn):
    """Re-run the ST_TR → ST_XTRANS.SUOMQTY overlay (same SQL as DB init). Safe to call from an admin API."""
    return _backfill_st_xtrans_suomqty_from_st_tr_udf(conn)


def _ensure_st_tr_push_suomqty_to_xtrans_trigger(conn):
    """
    When ``ST_TR`` rows are inserted/updated, refresh ``ST_XTRANS.SUOMQTY`` for transfer rows whose
    *to* document line (TODOCTYPE / TODOCKEY / TODTLKEY) matches that stock line.

    This keeps procurement SO/PO outstanding (which read ``ST_XTRANS.SUOMQTY``) current without
    restarting the app to re-run the one-time backfill.
    """
    st_fields = _get_relation_field_names(conn, "ST_TR")
    if not {"UDF_SUOMQTY", "DOCTYPE", "DOCKEY", "DTLKEY"}.issubset(st_fields):
        print("[DB INIT WARNING] ST_TR missing UDF_SUOMQTY or keys; TRG_ST_TR_PUSH_SUOMQTY_TO_XTRANS skipped")
        return False
    x_fields = _get_relation_field_names(conn, "ST_XTRANS")
    if not {"SUOMQTY", "TODOCTYPE", "TODOCKEY", "TODTLKEY"}.issubset(x_fields):
        print("[DB INIT WARNING] ST_XTRANS missing TODO* / SUOMQTY; TRG_ST_TR_PUSH_SUOMQTY_TO_XTRANS skipped")
        return False

    cur = conn.cursor()
    try:
        try:
            cur.execute("DROP TRIGGER TRG_ST_TR_PUSH_SUOMQTY_TO_XTRANS")
            conn.commit()
        except Exception:
            pass

        cur.execute(
            """
            CREATE TRIGGER TRG_ST_TR_PUSH_SUOMQTY_TO_XTRANS FOR ST_TR
            ACTIVE AFTER INSERT OR UPDATE POSITION 20
            AS
            BEGIN
              UPDATE ST_XTRANS X
              SET X.SUOMQTY = COALESCE((
                SELECT CAST(SUM(CAST(COALESCE(S2.UDF_SUOMQTY, 0) AS DOUBLE PRECISION)) AS DOUBLE PRECISION)
                FROM ST_TR S2
                WHERE TRIM(UPPER(COALESCE(S2.DOCTYPE, ''))) = TRIM(UPPER(COALESCE(X.TODOCTYPE, '')))
                  AND S2.DOCKEY = X.TODOCKEY
                  AND S2.DTLKEY = X.TODTLKEY
              ), 0)
              WHERE X.TODOCKEY IS NOT NULL
                AND X.TODTLKEY IS NOT NULL
                AND TRIM(COALESCE(X.TODOCTYPE, '')) <> ''
                AND TRIM(UPPER(COALESCE(X.TODOCTYPE, ''))) = TRIM(UPPER(COALESCE(NEW.DOCTYPE, '')))
                AND X.TODOCKEY = NEW.DOCKEY
                AND X.TODTLKEY = NEW.DTLKEY;
            END
            """
        )
        conn.commit()
        print(
            "[DB INIT] TRG_ST_TR_PUSH_SUOMQTY_TO_XTRANS: ST_TR postings refresh ST_XTRANS.SUOMQTY "
            "on matching TODOCTYPE/TODOCKEY/TODTLKEY"
        )
        return True
    except Exception as e:
        conn.rollback()
        print(f"[DB INIT WARNING] Could not create TRG_ST_TR_PUSH_SUOMQTY_TO_XTRANS: {e}")
        return False
    finally:
        cur.close()


def _ensure_st_xtrans_suomqty_sync_trigger(conn):
    """
    Ensure ST_XTRANS.SUOMQTY defaults to 0 when omitted.

    SUOMQTY is not interchangeable with SQTY/QTY, so the trigger must not infer
    from those fields. It only converts NULL to 0.
    """
    fields = _get_relation_field_names(conn, 'ST_XTRANS')
    if 'SUOMQTY' not in fields:
        print("[DB INIT WARNING] ST_XTRANS.SUOMQTY is missing; trigger skipped")
        return False

    cur = conn.cursor()
    try:
        try:
            cur.execute("DROP TRIGGER TRG_ST_XTRANS_SUOMQTY_SYNC")
            conn.commit()
        except Exception:
            pass

        cur.execute('''
        CREATE TRIGGER TRG_ST_XTRANS_SUOMQTY_SYNC FOR ST_XTRANS
        ACTIVE BEFORE INSERT OR UPDATE POSITION 0
        AS
        BEGIN
          IF (NEW.SUOMQTY IS NULL) THEN
            NEW.SUOMQTY = 0;
        END
        ''')
        conn.commit()
        print("[DB INIT] Trigger TRG_ST_XTRANS_SUOMQTY_SYNC created: NULL SUOMQTY defaults to 0 only")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'name in use' in error_msg:
            print("[DB INIT] Trigger TRG_ST_XTRANS_SUOMQTY_SYNC already exists")
            return True
        print(f"[DB INIT WARNING] Could not create TRG_ST_XTRANS_SUOMQTY_SYNC: {e}")
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
    # Ensure generators for draft header/detail keys exist.
    _execute_ddl(
        conn,
        'CREATE GENERATOR GEN_SL_QTDRAFT_ID',
        success_message='[DB INIT] GEN_SL_QTDRAFT_ID generator created.',
        ignore_if_contains=['already exists', 'name in use']
    )

    _execute_ddl(
        conn,
        'CREATE GENERATOR GEN_SL_QTDTLDRAFT_ID',
        success_message='[DB INIT] GEN_SL_QTDTLDRAFT_ID generator created.',
        ignore_if_contains=['already exists', 'name in use']
    )
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


def _ensure_ph_pq_status_trigger(conn):
    """Trigger on PH_PQ that enforces UDF_PQAPPROVED based on UDF_STATUS.

    Rules:
    - STATUS = 'PENDING'  -> UDF_PQAPPROVED = NULL
    - STATUS = 'APPROVED' -> UDF_PQAPPROVED = true/1/'1' (based on column type)
    - STATUS = 'CANCELLED' -> UDF_PQAPPROVED = false/0/'0' (based on column type)
    - Any other STATUS keeps UDF_PQAPPROVED unchanged.
    """
    cur = conn.cursor()
    try:
        try:
            cur.execute("DROP TRIGGER TRG_PH_PQ_STATUS_SYNC")
            conn.commit()
        except Exception:
            pass

        # Resolve UDF_PQAPPROVED type dynamically because different DBs define it
        # as BOOLEAN, CHAR/VARCHAR, or numeric.
        cur.execute(
            """
            SELECT F.RDB$FIELD_TYPE
            FROM RDB$RELATION_FIELDS RF
            JOIN RDB$FIELDS F ON RF.RDB$FIELD_SOURCE = F.RDB$FIELD_NAME
            WHERE RF.RDB$RELATION_NAME = 'PH_PQ' AND RF.RDB$FIELD_NAME = 'UDF_PQAPPROVED'
            """
        )
        row = cur.fetchone()
        field_type = int(row[0]) if row and row[0] is not None else None

        # Firebird field type codes used here:
        # BOOLEAN=23, CHAR=14, VARCHAR=37, CSTRING=40
        if field_type == 23:
            approved_literal = "TRUE"
            inactive_literal = "FALSE"
        elif field_type in (14, 37, 40):
            approved_literal = "'1'"
            inactive_literal = "'0'"
        else:
            approved_literal = "1"
            inactive_literal = "0"

        trigger_sql = f"""
        CREATE TRIGGER TRG_PH_PQ_STATUS_SYNC FOR PH_PQ
        ACTIVE BEFORE INSERT OR UPDATE POSITION 0
        AS
        DECLARE VARIABLE V_STATUS VARCHAR(60);
        BEGIN
          V_STATUS = UPPER(TRIM(COALESCE(NEW.UDF_STATUS, '')));

          IF (V_STATUS = 'PENDING') THEN
            NEW.UDF_PQAPPROVED = NULL;
                    ELSE IF (V_STATUS = 'APPROVED') THEN
            NEW.UDF_PQAPPROVED = {approved_literal};
                    ELSE IF (V_STATUS = 'CANCELLED') THEN
            NEW.UDF_PQAPPROVED = {inactive_literal};
        END
        """
        cur.execute(trigger_sql)
        conn.commit()
        print(
            "[DB INIT] Trigger TRG_PH_PQ_STATUS_SYNC created: "
            f"UDF_PQAPPROVED synced from UDF_STATUS on PH_PQ "
            f"(APPROVED={approved_literal}, CANCELLED={inactive_literal})"
        )
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'name in use' in error_msg:
            print("[DB INIT] Trigger TRG_PH_PQ_STATUS_SYNC already exists")
            return True
        print(f"[DB INIT WARNING] Could not create TRG_PH_PQ_STATUS_SYNC: {e}")
        return False
    finally:
        cur.close()


def _ensure_ph_pqdtl_defaults_trigger(conn):
    """Trigger on PH_PQDTL that sets TRANSFERABLE = NULL and UDF_PQAPPROVED = NULL on every INSERT."""
    cur = conn.cursor()
    try:
        try:
            cur.execute("DROP TRIGGER TRG_PH_PQDTL_DEFAULTS")
            conn.commit()
        except Exception:
            pass

        trigger_sql = f"""
        CREATE TRIGGER TRG_PH_PQDTL_DEFAULTS FOR PH_PQDTL
        ACTIVE BEFORE INSERT POSITION 0
        AS
        BEGIN
          NEW.TRANSFERABLE   = NULL;
          NEW.UDF_PQAPPROVED = NULL;
        END
        """
        cur.execute(trigger_sql)
        conn.commit()
        print("[DB INIT] Trigger TRG_PH_PQDTL_DEFAULTS created: TRANSFERABLE=NULL, UDF_PQAPPROVED=NULL on PH_PQDTL INSERT")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'name in use' in error_msg:
            print("[DB INIT] Trigger TRG_PH_PQDTL_DEFAULTS already exists")
            return True
        print(f"[DB INIT WARNING] Could not create TRG_PH_PQDTL_DEFAULTS: {e}")
        return False
    finally:
        cur.close()




def _ensure_procurement_bidding_tables(conn):
    """Create bidding tables (invite/header/detail/line-award) and related objects if missing."""
    _execute_ddl(
        conn,
        """
        CREATE TABLE PR_BID_INVITE (
            INVITE_ID INTEGER NOT NULL,
            REQUEST_DOCKEY INTEGER NOT NULL,
            REQUEST_NO VARCHAR(60),
            SUPPLIER_CODE VARCHAR(30) NOT NULL,
            SUPPLIER_NAME VARCHAR(160),
            STATUS VARCHAR(20),
            CREATED_BY VARCHAR(120),
            CREATED_AT TIMESTAMP,
            UPDATED_AT TIMESTAMP,
            PRIMARY KEY (INVITE_ID)
        )
        """,
        success_message='[DB INIT] PR_BID_INVITE table created.',
        ignore_if_contains=['already exists', 'name in use', 'table unknown']
    )
    _execute_ddl(
        conn,
        'CREATE GENERATOR GEN_PR_BID_INVITE_ID',
        success_message='[DB INIT] GEN_PR_BID_INVITE_ID generator created.',
        ignore_if_contains=['already exists', 'name in use']
    )
    _execute_ddl(
        conn,
        """
        CREATE TABLE PR_BID_HDR (
            BID_ID INTEGER NOT NULL,
            REQUEST_DOCKEY INTEGER NOT NULL,
            REQUEST_NO VARCHAR(60),
            SUPPLIER_CODE VARCHAR(30) NOT NULL,
            SUPPLIER_NAME VARCHAR(160),
            STATUS VARCHAR(20),
            REMARKS VARCHAR(500),
            UDF_REASON VARCHAR(500),
            CREATED_BY VARCHAR(120),
            CREATED_AT TIMESTAMP,
            APPROVED_BY VARCHAR(120),
            APPROVED_AT TIMESTAMP,
            PRIMARY KEY (BID_ID)
        )
        """,
        success_message='[DB INIT] PR_BID_HDR table created.',
        ignore_if_contains=['already exists', 'name in use', 'table unknown']
    )
    _execute_ddl(
        conn,
        'CREATE GENERATOR GEN_PR_BID_HDR_ID',
        success_message='[DB INIT] GEN_PR_BID_HDR_ID generator created.',
        ignore_if_contains=['already exists', 'name in use']
    )
    _execute_ddl(
        conn,
        """
        CREATE TABLE PR_BID_DTL (
            BID_DTL_ID INTEGER NOT NULL,
            BID_ID INTEGER NOT NULL,
            SOURCE_DTLKEY INTEGER NOT NULL,
            ITEMCODE VARCHAR(60),
            DESCRIPTION VARCHAR(255),
            BID_QTY NUMERIC(18, 2),
            BID_UNITPRICE NUMERIC(18, 2),
            BID_TAXAMT NUMERIC(18, 2),
            BID_AMOUNT NUMERIC(18, 2),
            LEAD_DAYS INTEGER,
            REMARKS VARCHAR(255),
            PRIMARY KEY (BID_DTL_ID)
        )
        """,
        success_message='[DB INIT] PR_BID_DTL table created.',
        ignore_if_contains=['already exists', 'name in use', 'table unknown']
    )
    _execute_ddl(
        conn,
        'CREATE GENERATOR GEN_PR_BID_DTL_ID',
        success_message='[DB INIT] GEN_PR_BID_DTL_ID generator created.',
        ignore_if_contains=['already exists', 'name in use']
    )
    _execute_ddl(
        conn,
        """
        CREATE TABLE PR_BID_LINE_AWARD (
            AWARD_ID INTEGER NOT NULL,
            REQUEST_DOCKEY INTEGER NOT NULL,
            DETAIL_ID INTEGER NOT NULL,
            BID_ID INTEGER NOT NULL,
            SUPPLIER_CODE VARCHAR(30),
            SUPPLIER_NAME VARCHAR(160),
            UDF_REASON VARCHAR(500),
            APPROVED_BY VARCHAR(120),
            APPROVED_AT TIMESTAMP,
            PRIMARY KEY (AWARD_ID)
        )
        """,
        success_message='[DB INIT] PR_BID_LINE_AWARD table created.',
        ignore_if_contains=['already exists', 'name in use', 'table unknown']
    )
    _execute_ddl(
        conn,
        'CREATE GENERATOR GEN_PR_BID_LINE_AWARD_ID',
        success_message='[DB INIT] GEN_PR_BID_LINE_AWARD_ID generator created.',
        ignore_if_contains=['already exists', 'name in use']
    )
    _execute_ddl(
        conn,
        'CREATE INDEX IX_PR_BID_INVITE_REQ_SUP ON PR_BID_INVITE (REQUEST_DOCKEY, SUPPLIER_CODE)',
        success_message='[DB INIT] IX_PR_BID_INVITE_REQ_SUP index created.',
        ignore_if_contains=['already exists', 'name in use']
    )
    _execute_ddl(
        conn,
        'CREATE INDEX IX_PR_BID_HDR_REQ ON PR_BID_HDR (REQUEST_DOCKEY)',
        success_message='[DB INIT] IX_PR_BID_HDR_REQ index created.',
        ignore_if_contains=['already exists', 'name in use']
    )
    _execute_ddl(
        conn,
        'CREATE INDEX IX_PR_BID_DTL_BID ON PR_BID_DTL (BID_ID)',
        success_message='[DB INIT] IX_PR_BID_DTL_BID index created.',
        ignore_if_contains=['already exists', 'name in use']
    )
    _execute_ddl(
        conn,
        'CREATE UNIQUE INDEX IX_PR_BID_AWARD_REQ_DTL ON PR_BID_LINE_AWARD (REQUEST_DOCKEY, DETAIL_ID)',
        success_message='[DB INIT] IX_PR_BID_AWARD_REQ_DTL unique index created.',
        ignore_if_contains=['already exists', 'name in use']
    )
    _execute_ddl(
        conn,
        'CREATE INDEX IX_PR_BID_AWARD_REQ ON PR_BID_LINE_AWARD (REQUEST_DOCKEY)',
        success_message='[DB INIT] IX_PR_BID_AWARD_REQ index created.',
        ignore_if_contains=['already exists', 'name in use']
    )
    _execute_ddl(
        conn,
        'ALTER TABLE PR_BID_HDR ADD UDF_REASON VARCHAR(500)',
        success_message='[DB INIT] PR_BID_HDR.UDF_REASON column added.',
        ignore_if_contains=['already exists', 'duplicate', 'column', 'unsuccessful']
    )


def _ensure_procurement_selected_supplier_table(conn):
    """Create PR_SELECTED_SUPPLIER table for draft/edit supplier selections if missing."""
    _execute_ddl(
        conn,
        """
        CREATE TABLE PR_SELECTED_SUPPLIER (
            ID INTEGER NOT NULL,
            REQUEST_DOCKEY INTEGER NOT NULL,
            REQUEST_NO VARCHAR(60),
            SUPPLIER_CODE VARCHAR(30) NOT NULL,
            SUPPLIER_NAME VARCHAR(160),
            SUPPLIER_EMAIL VARCHAR(255),
            CREATED_BY VARCHAR(120),
            CREATED_AT TIMESTAMP,
            UPDATED_AT TIMESTAMP,
            PRIMARY KEY (ID)
        )
        """,
        success_message='[DB INIT] PR_SELECTED_SUPPLIER table created.',
        ignore_if_contains=['already exists', 'name in use', 'table unknown']
    )
    _execute_ddl(
        conn,
        'CREATE GENERATOR GEN_PR_SELECTED_SUPPLIER_ID',
        success_message='[DB INIT] GEN_PR_SELECTED_SUPPLIER_ID generator created.',
        ignore_if_contains=['already exists', 'name in use']
    )
    _execute_ddl(
        conn,
        'CREATE INDEX IX_PR_SELECTED_SUP_REQ ON PR_SELECTED_SUPPLIER (REQUEST_DOCKEY)',
        success_message='[DB INIT] IX_PR_SELECTED_SUP_REQ index created.',
        ignore_if_contains=['already exists', 'name in use']
    )
    _execute_ddl(
        conn,
        'CREATE INDEX IX_PR_SELECTED_SUP_REQ_SUP ON PR_SELECTED_SUPPLIER (REQUEST_DOCKEY, SUPPLIER_CODE)',
        success_message='[DB INIT] IX_PR_SELECTED_SUP_REQ_SUP index created.',
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

        # Ensure SL_QT has REMARKS column for manual notes
        _ensure_sl_qt_remarks_column(conn)

        # Ensure SL_QTDTL has REMARKS column for item-level remarks
        _ensure_sl_qtdtl_remarks_column(conn)

        # Ensure AR_CUSTOMER has UDF_EMAIL for guest sign-in payload
        _ensure_ar_customer_udf_email_column(conn)


        # Ensure ST_ITEM has UDF_UOM for quotation item lookup queries
        _ensure_st_item_udf_uom_column(conn)
        
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

        # Keep SL_QT billing address fields in sync with delivery address fields
        _ensure_sl_qt_address_sync_trigger(conn)

        # Keep SL_QT.STATUS in sync with CANCELLED (-10 when cancelled, else 0)
        _ensure_sl_qt_cancelled_status_sync_trigger(conn)

        # Keep SL_QT.LOCALDOCAMT in sync with DOCAMT * CURRENCYRATE
        _ensure_sl_qt_localdocamt_sync_trigger(conn)

        # Keep SL_QTDTL.SQTY in sync with QTY * RATE
        _ensure_sl_qtdtl_sqty_sync_trigger(conn)

        # Keep SL_QTDTL.LOCALAMOUNT in sync with AMOUNT * SL_QT.CURRENCYRATE
        _ensure_sl_qtdtl_localamount_sync_trigger(conn)

        # ST_TR: optional UDF for secondary-UOM qty (populated alongside SQTY by stock posting)
        _ensure_st_tr_udf_suomqty_column(conn)
        _backfill_st_tr_udf_suomqty(conn)
        _ensure_st_tr_udf_suomqty_sync_trigger(conn)

        # ST_XTRANS.SUOMQTY: ensure column, NULL→0, then overlay from ST_TR.UDF_SUOMQTY (TODOCTYPE/TODOCKEY/TODTLKEY)
        _ensure_st_xtrans_suomqty_column(conn)
        _backfill_st_xtrans_suomqty(conn)
        _backfill_st_xtrans_suomqty_from_st_tr_udf(conn)
        _ensure_st_tr_push_suomqty_to_xtrans_trigger(conn)
        _ensure_st_xtrans_suomqty_sync_trigger(conn)

        # Ensure pricing priority rule settings table exists and is seeded
        _ensure_pricing_priority_rule_table(conn)
        _seed_pricing_priority_rules(conn)

        # Ensure PH_PQ status/approval triggers exist
        _ensure_ph_pq_status_trigger(conn)
        _ensure_ph_pqdtl_defaults_trigger(conn)

        # Ensure supplier bidding tables exist
        _ensure_procurement_bidding_tables(conn)

        # Ensure selected supplier persistence table exists for PR create/edit flows
        _ensure_procurement_selected_supplier_table(conn)

    except Exception as e:
        print(f"[DB INIT ERROR] {e}")
    finally:
        if conn:
            conn.close()
