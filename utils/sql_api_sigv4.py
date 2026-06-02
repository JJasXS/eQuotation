"""SigV4 service name resolution for SQL Accounting HTTP API (api.sql.my)."""
from __future__ import annotations

import os


def resolve_sql_api_sigv4_service(
    host: str | None,
    configured: str | None = None,
) -> str:
    """
    Return the AWS SigV4 ``service`` name for SQL API requests.

    ``api.sql.my`` expects ``sqlaccount``. Tenant Dynamo often stores ``execute-api``
    (API Gateway style), which produces intermittent HTTP 401 from the SQL cloud API.
    """
    h = (host or os.getenv("SQL_API_HOST") or "api.sql.my").strip().lower()
    cfg = (configured if configured is not None else os.getenv("SQL_API_SERVICE") or "").strip()
    if "api.sql.my" in h:
        if not cfg or cfg.lower() == "execute-api":
            return "sqlaccount"
    return cfg or "sqlaccount"
