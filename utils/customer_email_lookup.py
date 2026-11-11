"""Resolve AR_CUSTOMER identity from login email (branch + UDF_EMAIL* + EMAIL)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


def normalize_login_email(email: str | None) -> str:
    return str(email or "").strip()


@dataclass(frozen=True)
class CustomerEmailMatch:
    code: str
    source: str
    matched_column: str | None
    email: str
    department: str | None = None

    @property
    def udf_email_suffix(self) -> str:
        col = (self.matched_column or "").strip()
        m = re.fullmatch(r"UDF_EMAIL(\d*)", col, re.IGNORECASE)
        if not m:
            return ""
        return m.group(1) or ""


@dataclass(frozen=True)
class CustomerEmailLookupResult:
    match: CustomerEmailMatch | None
    ambiguous_codes: tuple[str, ...] = ()
    error: str | None = None

    @property
    def is_unique(self) -> bool:
        return self.match is not None and not self.ambiguous_codes and not self.error

    @property
    def customer_code(self) -> str | None:
        return self.match.code if self.match else None


def _table_has_column(cur: Any, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*)
        FROM RDB$RELATION_FIELDS
        WHERE TRIM(RDB$RELATION_NAME) = ?
          AND TRIM(RDB$FIELD_NAME) = ?
        """,
        [table.upper(), column.upper()],
    )
    row = cur.fetchone()
    return bool(row and int(row[0] or 0) > 0)


def sorted_ar_customer_udf_email_columns(cur: Any) -> list[str]:
    """UDF_EMAIL / UDF_EMAIL01 / … on AR_CUSTOMER, ordered by numeric suffix."""
    cur.execute(
        """
        SELECT TRIM(RDB$FIELD_NAME)
        FROM RDB$RELATION_FIELDS
        WHERE TRIM(RDB$RELATION_NAME) = 'AR_CUSTOMER'
        """,
    )
    cols = [str(r[0]).strip() for r in (cur.fetchall() or []) if r and r[0]]
    email_cols = [c for c in cols if re.fullmatch(r"UDF_EMAIL\d*", c, re.IGNORECASE)]

    def sort_key(c: str) -> tuple[int, str]:
        m = re.fullmatch(r"UDF_EMAIL(\d*)", c, re.IGNORECASE)
        if not m:
            return (10**9, c.upper())
        digits = m.group(1)
        return (int(digits, 10) if digits else 0, c.upper())

    return sorted(email_cols, key=sort_key)


def department_column_for_udf_email(email_col: str) -> str:
    m = re.fullmatch(r"UDF_EMAIL(\d*)", (email_col or "").strip(), re.IGNORECASE)
    if not m:
        return "UDF_DEPARTMENT"
    digits = m.group(1)
    return "UDF_DEPARTMENT" if not digits else f"UDF_DEPARTMENT{digits}"


def _add_match(
    matches: list[CustomerEmailMatch],
    *,
    code: Any,
    source: str,
    matched_column: str | None,
    email: Any,
    department: Any = None,
) -> None:
    code_s = str(code or "").strip()
    if not code_s:
        return
    matches.append(
        CustomerEmailMatch(
            code=code_s,
            source=source,
            matched_column=matched_column,
            email=str(email or "").strip(),
            department=(str(department).strip() if department is not None and str(department).strip() else None),
        )
    )


def lookup_customer_by_email(cur: Any, email: str | None) -> CustomerEmailLookupResult:
    """
    Case-insensitive, trimmed email match across:
    1) AR_CUSTOMERBRANCH.EMAIL
    2) AR_CUSTOMER UDF_EMAIL*
    3) AR_CUSTOMER.EMAIL

    Unique CODE → success. Multiple distinct CODEs → ambiguous (no silent pick).
    """
    normalized = normalize_login_email(email)
    if not normalized:
        return CustomerEmailLookupResult(match=None, error="email is required")

    matches: list[CustomerEmailMatch] = []

    try:
        cur.execute(
            """
            SELECT CODE, EMAIL
            FROM AR_CUSTOMERBRANCH
            WHERE UPPER(TRIM(EMAIL)) = UPPER(TRIM(?))
            """,
            [normalized],
        )
        for row in cur.fetchall() or []:
            _add_match(
                matches,
                code=row[0],
                source="AR_CUSTOMERBRANCH.EMAIL",
                matched_column=None,
                email=row[1],
            )
    except Exception:
        pass

    for email_col in sorted_ar_customer_udf_email_columns(cur):
        dept_col = department_column_for_udf_email(email_col)
        has_dept = _table_has_column(cur, "AR_CUSTOMER", dept_col)
        ec = email_col.upper()
        try:
            if has_dept:
                dc = dept_col.upper()
                cur.execute(
                    f"""
                    SELECT CODE, {ec}, {dc}
                    FROM AR_CUSTOMER
                    WHERE UPPER(TRIM({ec})) = UPPER(TRIM(?))
                    """,
                    [normalized],
                )
            else:
                cur.execute(
                    f"""
                    SELECT CODE, {ec}
                    FROM AR_CUSTOMER
                    WHERE UPPER(TRIM({ec})) = UPPER(TRIM(?))
                    """,
                    [normalized],
                )
            for row in cur.fetchall() or []:
                _add_match(
                    matches,
                    code=row[0],
                    source=f"AR_CUSTOMER.{email_col}",
                    matched_column=email_col,
                    email=row[1],
                    department=row[2] if has_dept and len(row) > 2 else None,
                )
        except Exception:
            continue

    try:
        if _table_has_column(cur, "AR_CUSTOMER", "EMAIL"):
            cur.execute(
                """
                SELECT CODE, EMAIL
                FROM AR_CUSTOMER
                WHERE UPPER(TRIM(EMAIL)) = UPPER(TRIM(?))
                """,
                [normalized],
            )
            for row in cur.fetchall() or []:
                _add_match(
                    matches,
                    code=row[0],
                    source="AR_CUSTOMER.EMAIL",
                    matched_column="EMAIL",
                    email=row[1],
                )
    except Exception:
        pass

    if not matches:
        return CustomerEmailLookupResult(match=None)

    by_code: dict[str, CustomerEmailMatch] = {}
    for m in matches:
        key = m.code.upper()
        # Prefer first discovery order (branch, then UDF numeric order, then EMAIL).
        by_code.setdefault(key, m)

    codes = tuple(sorted({m.code for m in matches}, key=lambda c: c.upper()))
    if len(codes) > 1:
        return CustomerEmailLookupResult(
            match=None,
            ambiguous_codes=codes,
            error=(
                "Email matches multiple customer codes: "
                + ", ".join(codes)
                + ". Contact administrator."
            ),
        )

    return CustomerEmailLookupResult(match=by_code[codes[0].upper()])


def lookup_customer_user_dict(cur: Any, email: str | None) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """
    Auth-compatible helper.

    Returns ``(user_dict, customer_code, error_message)``.
    On ambiguity, both user and code are None and error_message is set.
    """
    result = lookup_customer_by_email(cur, email)
    if result.error and result.ambiguous_codes:
        return None, None, result.error
    if not result.match:
        return None, None, result.error
    m = result.match
    user = {
        "code": m.code,
        "email": m.email,
        "source": m.source,
        "matched_udf_email_column": m.matched_column,
        "udf_email_suffix": m.udf_email_suffix,
    }
    if m.department:
        user["department"] = m.department
    return user, m.code, None
