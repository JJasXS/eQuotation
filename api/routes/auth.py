"""Authentication helper endpoints backed by Firebird lookups."""
import os
import sys

import fdb
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query

from api.routes.suppliers import _external_supplier_url, _make_sigv4_get

# Reuse Flask role helpers (same repo); FastAPI runs as separate process with same cwd.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from utils.role_permissions import (  # noqa: E402
    ACCESS_TIER_CUSTOMER,
    ACCESS_TIER_SUPPLIER,
    compute_access_tier,
    staff_has_any_mapped_role_udf,
    staff_udf_from_sy_user_row,
    user_type_for_session,
)


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


def _fetch_sy_user_profile_with_udfs(cur, normalized_email: str):
    """
    Return (row_dict, staff_udf) for SY_USER row matching email, including all UDF_* columns if present.
    row_dict is None when no SY_USER row.
    """
    cur.execute(
        """
        SELECT TRIM(RDB$FIELD_NAME)
        FROM RDB$RELATION_FIELDS
        WHERE RDB$RELATION_NAME = 'SY_USER' AND RDB$FIELD_NAME STARTING WITH 'UDF_'
        """,
    )
    udf_cols = [str(r[0]).strip() for r in (cur.fetchall() or []) if r and r[0]]

    base_cols = ["CODE", "NAME", "EMAIL", "ISACTIVE"]
    select_cols = base_cols + [c for c in udf_cols if c.upper() not in {x.upper() for x in base_cols}]
    col_sql = ", ".join(select_cols)
    cur.execute(
        f"""
        SELECT {col_sql}
        FROM SY_USER
        WHERE UPPER(TRIM(EMAIL)) = UPPER(TRIM(?))
        """,
        [normalized_email],
    )
    row = cur.fetchone()
    if not row:
        return None, {}
    row_dict = {select_cols[i]: row[i] for i in range(len(select_cols))}
    return row_dict, staff_udf_from_sy_user_row(row_dict)


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


def _lookup_supplier_by_email(cur, normalized_email: str):
    """AR_SUPPLIER / AP_SUPPLIER (+ external API fallback). Returns (supplier_dict|None, supplier_code|None)."""
    supplier = None
    supplier_code = None
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

    if not supplier:
        supplier, supplier_code = _lookup_supplier_via_external_api(normalized_email)
    return supplier, supplier_code


def _lookup_customer_by_email(cur, normalized_email: str):
    """AR_CUSTOMERBRANCH then AR_CUSTOMER (UDF_EMAIL, EMAIL). Returns (user_dict|None, customer_code|None)."""
    user = None
    customer_code = None
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
        return user, customer_code

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
            return user, customer_code
    except Exception:
        pass

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
    return user, customer_code


@router.get("/email-lookup")
def lookup_email_identity(
    email: str = Query(..., min_length=3, max_length=255),
    login_mode: str = Query(
        "customer",
        pattern="^(customer|admin|supplier)$",
        description="Which directory to search: customer (AR_*), admin (SY_USER), or supplier (AR_/AP_SUPPLIER).",
    ),
):
    """Resolve login email against one backend source, chosen by login_mode (login page tab)."""
    normalized_email = (email or "").strip()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="email is required")

    mode = (login_mode or "customer").strip().lower()
    if mode not in ("customer", "admin", "supplier"):
        mode = "customer"

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
        staff_udf: dict = {}
        sy_user_profile = None

        if mode == "admin":
            try:
                sy_user_profile, staff_udf = _fetch_sy_user_profile_with_udfs(cur, normalized_email)
            except Exception as exc:
                print(f"[AUTH] SY_USER profile read failed: {exc}", flush=True)
                sy_user_profile, staff_udf = None, {}
            if sy_user_profile:
                admin = {
                    "code": sy_user_profile.get("CODE"),
                    "name": sy_user_profile.get("NAME"),
                    "email": sy_user_profile.get("EMAIL"),
                    "isactive": sy_user_profile.get("ISACTIVE"),
                    "staff_udf": staff_udf,
                }
        elif mode == "supplier":
            supplier, supplier_code = _lookup_supplier_by_email(cur, normalized_email)
        else:
            user, customer_code = _lookup_customer_by_email(cur, normalized_email)

        is_admin_sy = bool(admin)
        is_user = bool(user)
        is_supplier = bool(supplier) and not is_admin_sy

        staff_any = staff_has_any_mapped_role_udf(staff_udf)
        if is_supplier:
            access_tier = ACCESS_TIER_SUPPLIER
        elif is_user:
            if staff_any and is_admin_sy:
                access_tier = compute_access_tier(
                    is_supplier=False,
                    is_customer=True,
                    staff_udf=staff_udf,
                    sy_user_row_present=True,
                )
            else:
                access_tier = ACCESS_TIER_CUSTOMER
        else:
            access_tier = compute_access_tier(
                is_supplier=False,
                is_customer=False,
                staff_udf=staff_udf if is_admin_sy else {},
                sy_user_row_present=is_admin_sy,
            )

        user_type_hint = user_type_for_session(access_tier)

        return {
            "success": True,
            "email": normalized_email,
            "login_mode": mode,
            "found": bool(is_admin_sy or is_user or is_supplier),
            "is_admin": is_admin_sy,
            "is_user": is_user,
            "is_customer": is_user,
            "is_supplier": is_supplier,
            "customer_code": customer_code,
            "supplier_code": supplier_code,
            "admin": admin,
            "user": user,
            "supplier": supplier,
            "staff_udf": staff_udf,
            "access_tier": access_tier,
            "user_type_hint": user_type_hint,
            "is_full_management_admin": bool(staff_udf.get("management")),
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
