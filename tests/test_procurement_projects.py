"""Procurement project dropdown must use SQL API GET /project/* only."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from utils.sql_api_projects import SqlApiProjectsError, fetch_projects_from_sql_api


@patch("utils.sql_api_projects.SqlAccountingApiClient")
@patch("utils.sql_api_projects.load_sql_accounting_api_settings")
def test_fetch_projects_from_sql_api_project_star(mock_settings, mock_client_cls):
    settings = mock_settings.return_value
    settings.access_key = "ak"
    settings.secret_key = "sk"
    settings.timeout_seconds = 10.0
    settings.resolved_list_get_url.return_value = "https://api.sql.my/project/*"

    client = mock_client_cls.return_value
    client.get_json.return_value = (
        200,
        {"data": [{"code": "NON-PROJECT", "description": "Non project", "isactive": True}]},
        "",
    )

    rows = fetch_projects_from_sql_api()
    assert len(rows) == 1
    assert rows[0]["code"] == "NON-PROJECT"
    assert settings.resolved_list_get_url.called


@patch("utils.sql_api_projects.load_sql_accounting_api_settings")
def test_fetch_projects_raises_without_keys(mock_settings):
    mock_settings.return_value.access_key = ""
    mock_settings.return_value.secret_key = ""
    with pytest.raises(SqlApiProjectsError, match="not configured"):
        fetch_projects_from_sql_api()


def test_main_uncached_does_not_use_env_fallback():
    from main import _fetch_procurement_projects_uncached

    with patch("utils.sql_api_projects.fetch_projects_from_sql_api") as mock_fetch:
        mock_fetch.return_value = [{"code": "NON-PROJECT", "description": "NON-PROJECT", "isactive": True}]
        rows = _fetch_procurement_projects_uncached()
    assert rows[0]["code"] == "NON-PROJECT"
    mock_fetch.assert_called_once()
