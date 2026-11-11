"""Customer email → CODE identity (branch + UDF_EMAIL* + ambiguity)."""
from __future__ import annotations

import re

from utils.customer_email_lookup import lookup_customer_by_email, lookup_customer_user_dict


class _Cursor:
    def __init__(self, *, branch=None, udf_cols=None, udf_rows=None, email_rows=None):
        self.branch = branch or []
        self.udf_cols = udf_cols or []
        self.udf_rows = {k.upper(): list(v) for k, v in (udf_rows or {}).items()}
        self.email_rows = email_rows or []
        self._sql = ""

    def execute(self, sql, params=None):
        self._sql = " ".join(str(sql).split())
        self._params = params

    def _udf_col_in_where(self) -> str | None:
        m = re.search(
            r"WHERE\s+UPPER\(TRIM\((\w+)\)\)\s*=\s*UPPER\(TRIM\(\?\)\)",
            self._sql,
            re.IGNORECASE,
        )
        return m.group(1).upper() if m else None

    def fetchall(self):
        sql = self._sql.upper()
        if "FROM AR_CUSTOMERBRANCH" in sql:
            return list(self.branch)
        if "FROM RDB$RELATION_FIELDS" in sql and "COUNT(*)" not in sql:
            return [(c,) for c in self.udf_cols]
        if "FROM AR_CUSTOMER" in sql and "WHERE" in sql:
            col = self._udf_col_in_where()
            if col and col in self.udf_rows:
                return list(self.udf_rows[col])
            if col == "EMAIL":
                return list(self.email_rows)
        return []

    def fetchone(self):
        if "COUNT(*)" in self._sql.upper():
            return (1,)
        rows = self.fetchall()
        return rows[0] if rows else None


def test_unique_udf_email01_match_case_insensitive_trim():
    cur = _Cursor(
        udf_cols=["UDF_EMAIL", "UDF_EMAIL01"],
        udf_rows={
            "UDF_EMAIL": [],
            "UDF_EMAIL01": [("300-B0003", "looiyonghang@gmail.com", "Sales")],
        },
    )
    result = lookup_customer_by_email(cur, "  LooiYongHang@gmail.com ")
    assert result.is_unique
    assert result.customer_code == "300-B0003"
    assert result.match is not None
    assert (result.match.matched_column or "").upper() == "UDF_EMAIL01"
    user, code, err = lookup_customer_user_dict(cur, "looiyonghang@gmail.com")
    assert err is None
    assert code == "300-B0003"
    assert user is not None
    assert (user.get("matched_udf_email_column") or "").upper() == "UDF_EMAIL01"


def test_branch_email_preferred_when_unique():
    cur = _Cursor(
        branch=[("300-A0001", "a@example.com")],
        udf_cols=["UDF_EMAIL01"],
        udf_rows={"UDF_EMAIL01": []},
    )
    result = lookup_customer_by_email(cur, "a@example.com")
    assert result.customer_code == "300-A0001"
    assert result.match is not None
    assert result.match.source == "AR_CUSTOMERBRANCH.EMAIL"


def test_ambiguous_codes_fail_closed():
    cur = _Cursor(
        branch=[("300-Y0001", "looiyonghang@gmail.com")],
        udf_cols=["UDF_EMAIL01"],
        udf_rows={"UDF_EMAIL01": [("300-B0003", "looiyonghang@gmail.com", None)]},
    )
    result = lookup_customer_by_email(cur, "looiyonghang@gmail.com")
    assert result.match is None
    assert set(result.ambiguous_codes) == {"300-Y0001", "300-B0003"}
    assert result.error and "multiple customer codes" in result.error.lower()
    user, code, err = lookup_customer_user_dict(cur, "looiyonghang@gmail.com")
    assert user is None and code is None and err


def test_quotation_ownership_uses_resolved_code():
    code = lookup_customer_by_email(
        _Cursor(
            udf_cols=["UDF_EMAIL01"],
            udf_rows={"UDF_EMAIL01": [("300-B0003", "looiyonghang@gmail.com", None)]},
        ),
        "looiyonghang@gmail.com",
    ).customer_code
    session_code = str(code or "").strip()
    assert session_code == "300-B0003"
    assert session_code != "300-Y0001"
