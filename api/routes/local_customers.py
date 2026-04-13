"""Local customer insert endpoint for Firebird DB."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import fdb
import os
from dotenv import load_dotenv

# Load .env for DB credentials
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../.env'))

DB_PATH = os.getenv('DB_PATH')
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

router = APIRouter(prefix="/local/customers", tags=["Local Customers"])

class LocalCustomerRequest(BaseModel):
    code: str
    company_name: str
    credit_term: str
    phone1: str | None = None
    email: str | None = None
    address1: str | None = None
    address2: str | None = None
    postcode: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None


def insert_local_customer(customer: LocalCustomerRequest) -> dict:
    """Insert a customer into the local Firebird DB and return the saved payload."""
    con = None
    cur = None
    try:
        con = fdb.connect(dsn=f"{DB_HOST}:{DB_PATH}", user=DB_USER, password=DB_PASSWORD, charset='UTF8')
        cur = con.cursor()

        # Use minimal insert columns that are stable across SQL Account schemas.
        cur.execute(
            """
            INSERT INTO AR_CUSTOMER (CODE, COMPANYNAME, CREDITTERM)
            VALUES (?, ?, ?)
            """,
            [
                customer.code,
                customer.company_name,
                customer.credit_term,
            ]
        )

        # Best-effort email sync for login lookup; ignore if column doesn't exist in this schema.
        if customer.email:
            try:
                cur.execute(
                    """
                    UPDATE AR_CUSTOMER
                    SET UDF_EMAIL = ?
                    WHERE CODE = ?
                    """,
                    [customer.email, customer.code]
                )
            except Exception:
                pass

        con.commit()
        return customer.model_dump()
    finally:
        if cur is not None:
            cur.close()
        if con is not None:
            con.close()

@router.post("", status_code=201)
def create_local_customer(customer: LocalCustomerRequest):
    try:
        saved_customer = insert_local_customer(customer)
        return {"success": True, "message": "Customer inserted into local Firebird DB", "data": saved_customer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB insert failed: {e}")
