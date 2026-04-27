"""Authentication helper endpoints backed by Firebird lookups."""
import os

import fdb
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query

from api.routes.suppliers import _external_supplier_url, _make_sigv4_get


load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

DB_PATH = os.getenv("DB_PATH")
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

router = APIRouter(prefix="/auth", tags=["Auth"])


def _lookup_supplier_via_external_api(normalized_email: str):
    """Fallback lookup against external supplier API by udf_email."""
    if not normalized_email:
        return None, None

    target = normalized_email.strip().upper()
    if not target:
        return None, None

    url = _external_supplier_url()
    offset = 0
    limit = 500
    max_pages = 20

    for _ in range(max_pages):
        try:
            resp = _make_sigv4_get(url, {"offset": offset, "limit": limit})
            if not resp.ok:
                print(f"[AUTH] external supplier fallback HTTP {resp.status_code} at offset={offset}", flush=True)
                break
            payload = resp.json()
        except Exception as exc:
            print(f"[AUTH] external supplier fallback failed: {exc}", flush=True)
            break

        rows = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(rows, list) or not rows:
            break

        for row in rows:
            row_email = str((row or {}).get("udf_email") or "").strip()
            if row_email and row_email.upper() == target:
                code = str((row or {}).get("code") or "").strip() or None
                name = str((row or {}).get("companyname") or "").strip() or code
                return (
                    {
                        "code": code,
                        "name": name,
                        "email": row_email,
                        "source": "external_supplier.udf_email",
                    },
                    code,
                )

        if len(rows) < limit:
            break
        offset += limit

    return None, None


def _connect_db():
    if not DB_PATH or not DB_HOST or not DB_USER or DB_PASSWORD is None:
        raise HTTPException(status_code=500, detail="Database credentials are not fully configured.")
    return fdb.connect(dsn=f"{DB_HOST}:{DB_PATH}", user=DB_USER, password=DB_PASSWORD, charset="UTF8")


def _table_has_column(cur, table_name: str, column_name: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM RDB$RELATION_FIELDS
        WHERE RDB$RELATION_NAME = ? AND RDB$FIELD_NAME = ?
        """,
        [table_name.upper(), column_name.upper()],
    )
    return cur.fetchone() is not None


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
        supplier = None
        customer_code = None
        supplier_code = None

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

        # Supplier lookup via whichever supplier table exists in this Firebird schema.
        supplier_lookup_sources = [
            ("AR_SUPPLIER", "UDF_EMAIL", "COMPANYNAME"),
            ("AP_SUPPLIER", "UDF_EMAIL", "COMPANYNAME"),
            ("AR_SUPPLIER", "EMAIL", "COMPANYNAME"),
            ("AP_SUPPLIER", "EMAIL", "COMPANYNAME"),
        ]
        for table_name, email_col, name_col in supplier_lookup_sources:
            try:
                if not _table_has_column(cur, table_name, "CODE"):
                    continue
                if not _table_has_column(cur, table_name, email_col):
                    continue
                if not _table_has_column(cur, table_name, name_col):
                    name_col = "CODE"

                cur.execute(
                    f"""
                    SELECT CODE, {name_col}, {email_col}
                    FROM {table_name}
                    WHERE UPPER(TRIM({email_col})) = UPPER(TRIM(?))
                    """,
                    [normalized_email],
                )
                supplier_row = cur.fetchone()
                if supplier_row:
                    supplier = {
                        "code": supplier_row[0],
                        "name": supplier_row[1],
                        "email": supplier_row[2],
                        "source": f"{table_name}.{email_col}",
                    }
                    supplier_code = supplier_row[0]
                    break
            except Exception as exc:
                print(f"[AUTH] supplier lookup failed on {table_name}.{email_col}: {exc}", flush=True)

        # Fallback to external supplier API source used by procurement pages.
        if not supplier:
            supplier, supplier_code = _lookup_supplier_via_external_api(normalized_email)

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
        is_supplier = bool(supplier) and not is_admin

        return {
            "success": True,
            "email": normalized_email,
            "found": bool(is_admin or is_user or is_supplier),
            "is_admin": is_admin,
            "is_user": is_user,
            "is_customer": is_user,
            "is_supplier": is_supplier,
            "customer_code": customer_code,
            "supplier_code": supplier_code,
            "admin": admin,
            "user": user,
            "supplier": supplier,
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
