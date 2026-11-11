"""View e-PR local PH_PQ list helpers for status tabs."""
from __future__ import annotations

from utils.procurement_purchase_request import (
    _view_pr_has_detail_lines_sql,
    _view_pr_tab_where_sql,
    normalize_view_pr_tab_status,
)


def test_normalize_view_pr_tab_status():
    assert normalize_view_pr_tab_status("cancelled") == "CANCELLED"
    assert normalize_view_pr_tab_status("Awaiting Approval") == "AWAITING"
    assert normalize_view_pr_tab_status("nope") == ""


def test_cancelled_tab_where_includes_all_udf_cancelled():
    sql, params = _view_pr_tab_where_sql(
        "CANCELLED",
        status_col="STATUS",
        udf_col="UDF_STATUS",
        status_is_numeric=True,
    )
    assert "UDF_STATUS" in sql
    assert params == ["CANCELLED"]


def test_draft_tab_excludes_cancelled_udf():
    sql, params = _view_pr_tab_where_sql(
        "DRAFT",
        status_col="STATUS",
        udf_col="UDF_STATUS",
        status_is_numeric=True,
    )
    assert "STATUS" in sql
    assert "DRAFT" in sql.upper() or params[0] == 0
    assert "UDF_STATUS" in sql


def test_view_pr_has_detail_lines_sql():
    sql = _view_pr_has_detail_lines_sql("DOCKEY", "DOCKEY")
    assert "EXISTS" in sql
    assert "PH_PQDTL" in sql
    assert _view_pr_has_detail_lines_sql("", "DOCKEY") == ""
    assert _view_pr_has_detail_lines_sql("DOCKEY", "") == ""
