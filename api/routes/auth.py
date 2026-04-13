"""Authentication helper endpoints backed by Firebird lookups."""
import os

import fdb
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query


load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

DB_PATH = os.getenv("DB_PATH")
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

router = APIRouter(prefix="/auth", tags=["Auth"])


def _connect_db():
    if not DB_PATH or not DB_HOST or not DB_USER or DB_PASSWORD is None:
        raise HTTPException(status_code=500, detail="Database credentials are not fully configured.")
    return fdb.connect(dsn=f"{DB_HOST}:{DB_PATH}", user=DB_USER, password=DB_PASSWORD, charset="UTF8")


@router.get("/email-lookup")
def lookup_email_identity(email: str = Query(..., min_length=3, max_length=255)):
    """Check whether an email exists as admin/customer and return identity details."""
    normalized_email = (email or "").strip()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="email is required")

    con = None
    cur = None
    try:
        con = _connect_db()
        cur = con.cursor()

        admin = None
        user = None
        customer_code = None

        # Admin lookup
        cur.execute(
            """
            SELECT CODE, NAME, EMAIL, ISACTIVE
            FROM SY_USER
            WHERE UPPER(TRIM(EMAIL)) = UPPER(TRIM(?))
            """,
            [normalized_email],
        )
        admin_row = cur.fetchone()
        if admin_row:
            admin = {
                "code": admin_row[0],
                "name": admin_row[1],
                "email": admin_row[2],
                "isactive": admin_row[3],
            }

        # User lookup priority: AR_CUSTOMERBRANCH.EMAIL
        cur.execute(
            """
            SELECT CODE, EMAIL
            FROM AR_CUSTOMERBRANCH
            WHERE UPPER(TRIM(EMAIL)) = UPPER(TRIM(?))
            """,
            [normalized_email],
        )
        user_row = cur.fetchone()
        if user_row:
            user = {
                "code": user_row[0],
                "email": user_row[1],
                "source": "AR_CUSTOMERBRANCH.EMAIL",
            }
            customer_code = user_row[0]

        # Fallback: AR_CUSTOMER.UDF_EMAIL
        if not user:
            try:
                cur.execute(
                    """
                    SELECT CODE, UDF_EMAIL
                    FROM AR_CUSTOMER
                    WHERE UPPER(TRIM(UDF_EMAIL)) = UPPER(TRIM(?))
                    """,
                    [normalized_email],
                )
                user_row = cur.fetchone()
                if user_row:
                    user = {
                        "code": user_row[0],
                        "email": user_row[1],
                        "source": "AR_CUSTOMER.UDF_EMAIL",
                    }
                    customer_code = user_row[0]
            except Exception:
                pass

        # Legacy fallback: AR_CUSTOMER.EMAIL
        if not user:
            try:
                cur.execute(
                    """
                    SELECT CODE, EMAIL
                    FROM AR_CUSTOMER
                    WHERE UPPER(TRIM(EMAIL)) = UPPER(TRIM(?))
                    """,
                    [normalized_email],
                )
                user_row = cur.fetchone()
                if user_row:
                    user = {
                        "code": user_row[0],
                        "email": user_row[1],
                        "source": "AR_CUSTOMER.EMAIL",
                    }
                    customer_code = user_row[0]
            except Exception:
                pass

        is_admin = bool(admin)
        is_user = bool(user)

        return {
            "success": True,
            "email": normalized_email,
            "found": bool(is_admin or is_user),
            "is_admin": is_admin,
            "is_user": is_user,
            "is_customer": is_user,
            "customer_code": customer_code,
            "admin": admin,
            "user": user,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Email lookup failed: {str(exc)}")
    finally:
        if cur is not None:
            cur.close()
        if con is not None:
            con.close()
