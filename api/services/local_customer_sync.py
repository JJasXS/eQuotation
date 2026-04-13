"""Local Firebird post-create sync helpers for customer fields."""
import os

import fdb
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../.env'))

DB_PATH = os.getenv('DB_PATH')
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')


class LocalCustomerSyncRequest(BaseModel):
    code: str
    area: str | None = None
    currency_code: str | None = None
    tin: str | None = None
    brn2: str | None = None
    sales_tax_no: str | None = None
    service_tax_no: str | None = None
    tax_exp_date: str | None = None
    tax_exempt_no: str | None = None
    idtype: int | None = None
    attention: str | None = None
    address1: str | None = None
    address2: str | None = None
    address3: str | None = None
    address4: str | None = None
    postcode: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None


def sync_local_customer_fields(customer: LocalCustomerSyncRequest) -> dict:
    """Update local Firebird customer + billing branch fields after remote create."""
    con = None
    cur = None
    try:
        con = fdb.connect(dsn=f"{DB_HOST}:{DB_PATH}", user=DB_USER, password=DB_PASSWORD, charset='UTF8')
        cur = con.cursor()

        customer_updates = []
        customer_values = []
        mapping = [
            ("AREA", customer.area),
            ("CURRENCYCODE", customer.currency_code),
            ("TIN", customer.tin),
            ("BRN2", customer.brn2),
            ("SALESTAXNO", customer.sales_tax_no),
            ("SERVICETAXNO", customer.service_tax_no),
            ("TAXEXPDATE", customer.tax_exp_date),
            ("TAXEXEMPTNO", customer.tax_exempt_no),
            ("IDTYPE", customer.idtype),
        ]
        for column, value in mapping:
            if value not in (None, ""):
                customer_updates.append(f"{column} = ?")
                customer_values.append(value)

        if customer_updates:
            cur.execute(
                f"UPDATE AR_CUSTOMER SET {', '.join(customer_updates)} WHERE CODE = ?",
                customer_values + [customer.code],
            )

        branch_updates = []
        branch_values = []
        branch_mapping = [
            ("ATTENTION", customer.attention),
            ("ADDRESS1", customer.address1),
            ("ADDRESS2", customer.address2),
            ("ADDRESS3", customer.address3),
            ("ADDRESS4", customer.address4),
            ("POSTCODE", customer.postcode),
            ("CITY", customer.city),
            ("STATE", customer.state),
            ("COUNTRY", customer.country),
        ]
        for column, value in branch_mapping:
            if value not in (None, ""):
                branch_updates.append(f"{column} = ?")
                branch_values.append(value)

        if branch_updates:
            cur.execute(
                f"UPDATE AR_CUSTOMERBRANCH SET {', '.join(branch_updates)} WHERE CODE = ? AND BRANCHTYPE = 'B'",
                branch_values + [customer.code],
            )

        con.commit()
        return read_local_customer_fields(customer.code)
    finally:
        if cur is not None:
            cur.close()
        if con is not None:
            con.close()


def read_local_customer_fields(code: str) -> dict:
    """Read back persisted customer + branch fields from local Firebird."""
    con = None
    cur = None
    try:
        con = fdb.connect(dsn=f"{DB_HOST}:{DB_PATH}", user=DB_USER, password=DB_PASSWORD, charset='UTF8')
        cur = con.cursor()
        cur.execute(
            """
            SELECT CODE, AREA, CURRENCYCODE, TIN, BRN2, SALESTAXNO, SERVICETAXNO, TAXEXPDATE, TAXEXEMPTNO, IDTYPE
            FROM AR_CUSTOMER
            WHERE CODE = ?
            """,
            [code],
        )
        customer_row = cur.fetchone()

        cur.execute(
            """
            SELECT ATTENTION, ADDRESS1, ADDRESS2, ADDRESS3, ADDRESS4, POSTCODE, CITY, STATE, COUNTRY
            FROM AR_CUSTOMERBRANCH
            WHERE CODE = ?
            ORDER BY DTLKEY
            """,
            [code],
        )
        branch_row = cur.fetchone()

        result = {
            "code": code,
            "area": None,
            "currencycode": None,
            "tin": None,
            "brn2": None,
            "salestaxno": None,
            "servicetaxno": None,
            "taxexpdate": None,
            "taxexemptno": None,
            "idtype": None,
            "attention": None,
            "address1": None,
            "address2": None,
            "address3": None,
            "address4": None,
            "postcode": None,
            "city": None,
            "state": None,
            "country": None,
        }

        if customer_row:
            result.update({
                "code": customer_row[0],
                "area": customer_row[1],
                "currencycode": customer_row[2],
                "tin": customer_row[3],
                "brn2": customer_row[4],
                "salestaxno": customer_row[5],
                "servicetaxno": customer_row[6],
                "taxexpdate": str(customer_row[7]) if customer_row[7] is not None else None,
                "taxexemptno": customer_row[8],
                "idtype": customer_row[9],
            })

        if branch_row:
            result.update({
                "attention": branch_row[0],
                "address1": branch_row[1],
                "address2": branch_row[2],
                "address3": branch_row[3],
                "address4": branch_row[4],
                "postcode": branch_row[5],
                "city": branch_row[6],
                "state": branch_row[7],
                "country": branch_row[8],
            })

        return result
    finally:
        if cur is not None:
            cur.close()
        if con is not None:
            con.close()
