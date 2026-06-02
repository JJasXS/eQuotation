"""SQL Accounting GET /project/* — project codes for e-Procurement (SQL API only)."""
from __future__ import annotations

import os
from typing import Any

from api.clients import SqlAccountingApiClient, SqlAccountingApiError
from api.config import load_sql_accounting_api_settings


class SqlApiProjectsError(RuntimeError):
    """SQL API project list could not be loaded."""


def _parse_project_list_json(parsed: Any) -> list[dict[str, Any]]:
    if isinstance(parsed, list):
        raw_list = parsed
    elif isinstance(parsed, dict):
        raw_list = parsed.get("data")
        if raw_list is None:
            raw_list = parsed.get("items") or parsed.get("results")
    else:
        return []
    if not isinstance(raw_list, list):
        return []
    return [r for r in raw_list if isinstance(r, dict)]


def _normalize_project_row(row: dict[str, Any]) -> dict[str, Any] | None:
    code = str(row.get("code") or row.get("CODE") or "").strip()
    if not code:
        return None
    description = str(row.get("description") or row.get("DESCRIPTION") or "").strip()
    isactive = row.get("isactive")
    if isactive is None:
        isactive = row.get("ISACTIVE")
    if isactive is None:
        isactive = True
    if not bool(isactive):
        return None
    return {
        "code": code,
        "description": description or code,
        "isactive": True,
    }


def _project_list_path() -> str:
    raw = (os.getenv("SQL_API_PROJECT_LIST_PATH") or "/project/*").strip()
    if not raw.startswith("/"):
        raw = "/" + raw
    return raw


def fetch_projects_from_sql_api() -> list[dict[str, Any]]:
    """
    Load active projects from SQL Accounting SigV4 GET ``/project/*`` only.

    Raises ``SqlApiProjectsError`` when keys are missing or the API does not return HTTP 200.
    """
    settings = load_sql_accounting_api_settings()
    if not settings.access_key or not settings.secret_key:
        raise SqlApiProjectsError(
            "SQL API keys are not configured. Set SQL_API_ACCESS_KEY and SQL_API_SECRET_KEY."
        )

    client = SqlAccountingApiClient(settings)
    configured = _project_list_path()
    path_candidates: list[str] = []
    if configured:
        path_candidates.append(configured)
    for alt in ("/project/*", "/project"):
        if alt not in path_candidates:
            path_candidates.append(alt)

    last_status: int | None = None
    last_snippet = ""
    seen_urls: set[str] = set()

    for list_path in path_candidates:
        url = settings.resolved_list_get_url(list_path)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        try:
            status, parsed, raw = client.get_json(
                url,
                timeout_seconds=min(15.0, settings.timeout_seconds + 5.0),
            )
        except SqlAccountingApiError as exc:
            last_snippet = str(exc)
            continue

        last_status = status
        if status != 200:
            last_snippet = (raw or "")[:300].replace("\n", " ")
            continue

        normalized: list[dict[str, Any]] = []
        seen_codes: set[str] = set()
        for row in _parse_project_list_json(parsed):
            item = _normalize_project_row(row)
            if not item:
                continue
            code = item["code"]
            if code in seen_codes:
                continue
            seen_codes.add(code)
            normalized.append(item)

        if normalized:
            return normalized

    hint = f" (last HTTP {last_status})" if last_status is not None else ""
    raise SqlApiProjectsError(
        f"SQL API project list returned no rows from {path_candidates!r}{hint}: {last_snippet}"
    )
