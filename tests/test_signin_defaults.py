import json
import os
import sys
from datetime import datetime

import fdb
import requests
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.db_utils import build_firebird_dsn


load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

BASE_API_URL = os.getenv('BASE_API_URL', 'http://localhost').rstrip('/')
DB_PATH = os.getenv('DB_PATH')
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return int(value) != 0
    text = str(value).strip().lower()
    return text in {'1', 'true', 't', 'y', 'yes'}


def _build_payload(area_code, currency_symbol):
    now = datetime.now().strftime('%m%d%H%M%S')
    # BRN2 must be exactly 12 digits.
    brn2 = f"7{now:0>11}"[-12:]
    unique_tag = datetime.now().strftime('%Y%m%d%H%M%S')

    return {
        'COMPANYNAME': f'Default Test Co {unique_tag}',
        'AREA': area_code,
        'CURRENCYCODE': currency_symbol,
        'UDF_EMAIL': f'default.test.{unique_tag}@example.com',
        'BRN': f'BRN{unique_tag[-6:]}',
        'BRN2': brn2,
        'TIN': f'TIN{unique_tag[-6:]}',
        'CUSTOMERCODE': '',
        'ADDRESS1': 'No. 1 Test Street',
        'ADDRESS2': 'Unit A',
        'ADDRESS3': '',
        'ADDRESS4': '',
        'POSTCODE': '43000',
        'ATTENTION': 'Integration Tester',
        'PHONE1': '0123456789',
    }


def _get_db_connection():
    dsn = build_firebird_dsn(DB_PATH, DB_HOST)
    return fdb.connect(dsn=dsn, user=DB_USER, password=DB_PASSWORD, charset='UTF8')


def _resolve_valid_area_and_currency(con):
    cur = con.cursor()
    try:
        cur.execute(
            """
            SELECT FIRST 1 TRIM(CODE)
            FROM AREA
            WHERE CODE IS NOT NULL
              AND TRIM(CODE) <> ''
              AND CHAR_LENGTH(
                    REPLACE(REPLACE(REPLACE(REPLACE(TRIM(CODE), '-', ''), ' ', ''), '.', ''), '/', '')
                  ) >= 3
            """
        )
        area_row = cur.fetchone()
        if not area_row or not area_row[0]:
            raise RuntimeError('No valid AREA.CODE found in AREA table.')

        cur.execute("SELECT FIRST 1 TRIM(SYMBOL) FROM CURRENCY WHERE SYMBOL IS NOT NULL AND TRIM(SYMBOL) <> ''")
        currency_row = cur.fetchone()
        if not currency_row or not currency_row[0]:
            raise RuntimeError('No valid CURRENCY.SYMBOL found in CURRENCY table.')

        return str(area_row[0]).strip(), str(currency_row[0]).strip()
    finally:
        cur.close()


def _assert_equal(name, actual, expected):
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")


def main():
    print('=' * 80)
    print('TEST: Sign-in Defaults + BRN2->IDNO Trigger')
    print('=' * 80)

    if not DB_PATH or not DB_USER or not DB_PASSWORD:
        raise RuntimeError('Missing DB config in .env (DB_PATH, DB_USER, DB_PASSWORD).')

    con_for_defaults = _get_db_connection()
    try:
        valid_area, valid_currency = _resolve_valid_area_and_currency(con_for_defaults)
    finally:
        con_for_defaults.close()

    payload = _build_payload(valid_area, valid_currency)
    print('\n[1] Creating user via sign-in endpoint')
    print('Payload:')
    print(json.dumps(payload, indent=2))

    candidate_urls = [
        f"{BASE_API_URL}/api/create_signin_user",
        "http://localhost:5000/api/create_signin_user",
        f"{BASE_API_URL}/php/createSignInUser.php",
        "http://localhost/php/createSignInUser.php",
    ]

    response = None
    used_url = None
    for url in candidate_urls:
        try:
            trial = requests.post(url, json=payload, timeout=20)
            print(f"Tried: {url} -> {trial.status_code}")
            if trial.status_code < 500 and trial.status_code != 404:
                response = trial
                used_url = url
                break
            response = trial
            used_url = url
        except Exception as ex:
            print(f"Tried: {url} -> ERROR: {ex}")

    if response is None:
        raise RuntimeError('No endpoint reachable for sign-in test.')

    print(f"Using endpoint: {used_url}")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")

    if response.status_code >= 400:
        raise RuntimeError('Sign-in call failed, cannot continue checks.')

    data = response.json()
    if not data.get('success'):
        raise RuntimeError(f"API did not succeed: {data}")

    customer_code = data.get('customerCode')
    if not customer_code:
        raise RuntimeError('API success but customerCode missing in response.')

    print(f"\n[2] Verifying AR_CUSTOMER row for CODE={customer_code}")

    con = _get_db_connection()
    cur = con.cursor()
    try:
        cur.execute(
            '''
            SELECT
                CONTROLACCOUNT,
                AGENT,
                COMPANYCATEGORY,
                SUBMISSIONTYPE,
                AGINGON,
                ALLOWEXCEEDCREDITLIMIT,
                ADDPDCTOCRLIMIT,
                OUTSTANDING,
                STATEMENTTYPE,
                OVERDUELIMIT,
                CREDITLIMIT,
                IDTYPE,
                BRN2,
                IDNO,
                STATUS,
                UDF_EMAIL
            FROM AR_CUSTOMER
            WHERE CODE = ?
            ''',
            (customer_code,)
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f'AR_CUSTOMER row not found for CODE={customer_code}')

        (
            control_account,
            agent,
            company_category,
            submission_type,
            agingon,
            allow_exceed,
            add_pdc,
            outstanding,
            statement_type,
            over_due_limit,
            credit_limit,
            idtype,
            brn2,
            idno,
            status,
            udf_email,
        ) = row

        _assert_equal('CONTROLACCOUNT', str(control_account).strip(), '300-000')
        _assert_equal('AGENT', str(agent).strip(), '----')
        _assert_equal('COMPANYCATEGORY', str(company_category).strip(), '----')
        _assert_equal('SUBMISSIONTYPE', int(submission_type), 17)
        _assert_equal('AGINGON', str(agingon).strip(), 'I')
        _assert_equal('ALLOWEXCEEDCREDITLIMIT', _to_bool(allow_exceed), True)
        _assert_equal('ADDPDCTOCRLIMIT', _to_bool(add_pdc), True)
        _assert_equal('OUTSTANDING', float(outstanding), 0.0)
        _assert_equal('STATEMENTTYPE', str(statement_type).strip(), 'O')
        _assert_equal('OVERDUELIMIT', float(over_due_limit), 0.0)
        _assert_equal('CREDITLIMIT', float(credit_limit), 30000.0)
        _assert_equal('IDTYPE', int(idtype), 1)
        _assert_equal('BRN2', str(brn2).strip(), payload['BRN2'])
        _assert_equal('IDNO', str(idno).strip(), payload['BRN2'])
        _assert_equal('STATUS', str(status).strip(), 'P')
        _assert_equal('UDF_EMAIL', str(udf_email).strip(), payload['UDF_EMAIL'])

        print('[OK] All AR_CUSTOMER default values verified.')

        print('\n[3] Verifying trigger TRG_AR_CUSTOMER_BRN2_IDNO exists and active')
        cur.execute(
            '''
            SELECT RDB$TRIGGER_NAME, RDB$TRIGGER_INACTIVE
            FROM RDB$TRIGGERS
            WHERE RDB$TRIGGER_NAME = 'TRG_AR_CUSTOMER_BRN2_IDNO'
            '''
        )
        trg = cur.fetchone()
        if not trg:
            raise RuntimeError('Trigger TRG_AR_CUSTOMER_BRN2_IDNO not found.')

        trigger_name = str(trg[0]).strip()
        inactive = int(trg[1]) if trg[1] is not None else 0
        _assert_equal('TRIGGER_NAME', trigger_name, 'TRG_AR_CUSTOMER_BRN2_IDNO')
        _assert_equal('TRIGGER_INACTIVE', inactive, 0)
        print('[OK] Trigger exists and is active.')

    finally:
        cur.close()
        con.close()

    print('\n' + '=' * 80)
    print('PASS: Sign-in defaults and trigger checks succeeded.')
    print('=' * 80)


if __name__ == '__main__':
    main()
