"""Phase 2.4e — LocalOnly award sync (skip paid REST; preserve local awards)."""
from __future__ import annotations

from typing import Any

import pytest

from api.config.sql_accounting_pr_award_sync import (
    AWARD_SYNC_LOCAL_ONLY,
    AWARD_SYNC_REST,
    SqlAccountingPrAwardSyncSettings,
    load_sql_accounting_pr_award_sync_settings,
    normalize_award_sync_mode,
    verify_local_only_company_identity,
)
from api.config.sql_accounting_pr_write import (
    PROVIDER_REST,
    PROVIDER_SDK,
    SqlAccountingPurchaseRequestWriteSettings,
)
from utils.procurement_sql_api_sync import sync_purchase_request_sql_api_after_awards


def _multi_award_body() -> dict[str, Any]:
    return {
        "dockey": 80,
        "docno": "PR-26110004",
        "docnoex": "PR-26110004",
        "code": "----",
        "companyname": "",
        "udf_status": "APPROVED",
        "docamt": "42.00",
        "sdsdocdetail": [
            {
                "dtlkey": 4,
                "itemcode": "ITEM-A",
                "qty": "2",
                "unitprice": "10",
                "amount": "20",
                "udf_supcode": "400-L0014",
                "udf_supname": "LYH yong",
            },
            {
                "dtlkey": 5,
                "itemcode": "ITEM-B",
                "qty": "1",
                "unitprice": "22",
                "amount": "22",
                "udf_supcode": "400-A0001",
                "udf_supname": "ANOZ ALUMINIUM",
            },
            {
                "dtlkey": 6,
                "itemcode": "ITEM-C",
                "qty": "3",
                "unitprice": "0",
                "amount": "0",
                # partial award: no supplier yet
            },
        ],
        "changed": False,
    }


def _install_local_body(monkeypatch, body: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = body if body is not None else _multi_award_body()
    monkeypatch.setattr(
        "utils.procurement_sql_api_sync._all_local_pqdtl_keys",
        lambda dockey: {int(ln["dtlkey"]) for ln in payload["sdsdocdetail"]},
    )
    monkeypatch.setattr(
        "utils.procurement_sql_api_sync._build_purchaserequest_body_from_local",
        lambda dockey, keep_dtlkeys=None: (payload["docno"], dict(payload)),
    )
    return payload


def test_normalize_award_sync_mode_defaults_to_rest():
    assert normalize_award_sync_mode(None) == AWARD_SYNC_REST
    assert normalize_award_sync_mode("") == AWARD_SYNC_REST
    assert normalize_award_sync_mode("rest") == AWARD_SYNC_REST
    assert normalize_award_sync_mode("LocalOnly") == AWARD_SYNC_LOCAL_ONLY
    assert normalize_award_sync_mode("localonly") == AWARD_SYNC_LOCAL_ONLY


def test_load_award_sync_settings_default_rest(monkeypatch):
    monkeypatch.delenv("SQL_ACCOUNTING_PR_AWARD_SYNC_MODE", raising=False)
    settings = load_sql_accounting_pr_award_sync_settings()
    assert settings.mode == AWARD_SYNC_REST
    assert settings.is_rest is True
    assert settings.is_local_only is False


def test_verify_identity_requires_allowlist(monkeypatch):
    monkeypatch.setenv("DB_PATH", r"C:/eStream/SQLAccounting/DB/ACC-ANOZ.FDB")
    monkeypatch.delenv("SQL_ACCOUNTING_PR_AWARD_LOCAL_ONLY_DATABASE", raising=False)
    monkeypatch.delenv("SQL_ACCOUNTING_PR_AWARD_LOCAL_ONLY_DATABASES", raising=False)
    check = verify_local_only_company_identity()
    assert check.ok is False
    assert "LOCAL_ONLY_DATABASE" in check.reason


def test_verify_identity_rejects_mismatch_basename(monkeypatch):
    check = verify_local_only_company_identity(
        db_path=r"C:/db/ACC-OTHER.FDB",
        allowed_raw="ACC-ANOZ.FDB",
        sdk_database_file="",
    )
    assert check.ok is False
    assert "ACC-OTHER.FDB" in check.reason


def test_verify_identity_rejects_sdk_db_mismatch():
    check = verify_local_only_company_identity(
        db_path=r"C:/db/ACC-ANOZ.FDB",
        allowed_raw="ACC-ANOZ.FDB",
        sdk_database_file="ACC-UAMAT.FDB",
    )
    assert check.ok is False
    assert "does not match" in check.reason


def test_verify_identity_accepts_anoz():
    check = verify_local_only_company_identity(
        db_path=r"C:/eStream/SQLAccounting/DB/ACC-ANOZ.FDB",
        allowed_raw="ACC-ANOZ.FDB",
        sdk_database_file="ACC-ANOZ.FDB",
    )
    assert check.ok is True
    assert check.local_database == "ACC-ANOZ.FDB"


def test_local_only_skips_paid_rest_and_preserves_award_udfs(monkeypatch):
    payload = _install_local_body(monkeypatch)
    monkeypatch.setattr(
        "api.config.sql_accounting_pr_award_sync.load_sql_accounting_pr_award_sync_settings",
        lambda: SqlAccountingPrAwardSyncSettings(mode=AWARD_SYNC_LOCAL_ONLY),
    )
    monkeypatch.setattr(
        "api.config.sql_accounting_pr_award_sync.verify_local_only_company_identity",
        lambda: type(
            "C",
            (),
            {"ok": True, "local_database": "ACC-ANOZ.FDB", "reason": "ok"},
        )(),
    )

    rest_hits = {"n": 0}

    def _boom(*_a, **_k):
        rest_hits["n"] += 1
        raise AssertionError("paid REST must not run in LocalOnly")

    monkeypatch.setattr("utils.procurement_sql_api_sync.SqlAccountingApiClient", _boom)
    monkeypatch.setattr("utils.procurement_sql_api_sync._get_document", _boom)
    monkeypatch.setattr("utils.procurement_sql_api_sync._put_document", _boom)
    monkeypatch.setattr(
        "utils.procurement_sql_api_sync._sync_purchase_request_after_awards_via_sdk",
        _boom,
    )

    result = sync_purchase_request_sql_api_after_awards(80, keep_dtlkeys={4, 5, 6})
    assert result["synced"] is True
    assert result["mode"] == "localOnly"
    assert result["skippedPaidRest"] is True
    assert result["skippedSdkRewrite"] is True
    assert result["write_provider"] == AWARD_SYNC_LOCAL_ONLY
    assert result["companyDatabase"] == "ACC-ANOZ.FDB"
    assert result["dockey"] == 80
    assert result["docno"] == payload["docno"]
    assert result["lineCount"] == 3
    assert result["awardLineCount"] == 2
    assert result["udfStatus"] == "APPROVED"
    assert rest_hits["n"] == 0
    # Local body (source of Firebird awards) still has multi-supplier UDFs.
    assert payload["sdsdocdetail"][0]["udf_supcode"] == "400-L0014"
    assert payload["sdsdocdetail"][1]["udf_supcode"] == "400-A0001"
    assert "udf_supcode" not in payload["sdsdocdetail"][2]


def test_local_only_fails_closed_on_identity_mismatch_without_rest(monkeypatch):
    _install_local_body(monkeypatch)
    monkeypatch.setattr(
        "api.config.sql_accounting_pr_award_sync.load_sql_accounting_pr_award_sync_settings",
        lambda: SqlAccountingPrAwardSyncSettings(mode=AWARD_SYNC_LOCAL_ONLY),
    )
    monkeypatch.setattr(
        "api.config.sql_accounting_pr_award_sync.verify_local_only_company_identity",
        lambda: type(
            "C",
            (),
            {"ok": False, "local_database": "ACC-OTHER.FDB", "reason": "basename mismatch"},
        )(),
    )
    rest_hits = {"n": 0}

    def _boom(*_a, **_k):
        rest_hits["n"] += 1
        raise AssertionError("must not fall back to REST")

    monkeypatch.setattr("utils.procurement_sql_api_sync.SqlAccountingApiClient", _boom)
    monkeypatch.setattr(
        "utils.procurement_sql_api_sync._sync_purchase_request_after_awards_via_sdk",
        _boom,
    )

    with pytest.raises(RuntimeError, match="LocalOnly award sync refused"):
        sync_purchase_request_sql_api_after_awards(80, keep_dtlkeys={4})
    assert rest_hits["n"] == 0


def test_rest_mode_still_posts_when_missing(monkeypatch):
    payload = _install_local_body(monkeypatch)
    monkeypatch.setattr(
        "api.config.sql_accounting_pr_award_sync.load_sql_accounting_pr_award_sync_settings",
        lambda: SqlAccountingPrAwardSyncSettings(mode=AWARD_SYNC_REST),
    )
    monkeypatch.setattr(
        "api.config.sql_accounting_pr_write.load_sql_accounting_pr_write_settings",
        lambda: SqlAccountingPurchaseRequestWriteSettings(
            provider=PROVIDER_REST, block_rest_http=False, cud_enabled=False
        ),
    )
    posts: list[dict] = []

    class _Settings:
        access_key = "ak"
        secret_key = "sk"
        timeout_seconds = 10.0
        host = "localhost"
        use_tls = False

    class _Client:
        def __init__(self, _settings):
            pass

        def post_json(self, _url, body, timeout_seconds=0):
            posts.append(dict(body))
            return 200, {"dockey": 80, "docno": payload["docno"]}, "ok"

    monkeypatch.setattr(
        "utils.procurement_sql_api_sync.load_sql_accounting_api_settings",
        lambda: _Settings(),
    )
    monkeypatch.setattr("utils.procurement_sql_api_sync.SqlAccountingApiClient", _Client)
    monkeypatch.setattr("utils.procurement_sql_api_sync._get_document", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "utils.procurement_sql_api_sync._api_root_url",
        lambda *_a, **_k: "http://localhost/purchaserequest",
    )

    result = sync_purchase_request_sql_api_after_awards(80, keep_dtlkeys={4, 5, 6})
    assert result["synced"] is True
    assert result["mode"] == "post"
    assert result["write_provider"] == PROVIDER_REST
    assert len(posts) == 1
    assert posts[0]["sdsdocdetail"][0]["udf_supcode"] == "400-L0014"
    assert posts[0]["sdsdocdetail"][1]["udf_supcode"] == "400-A0001"
    assert posts[0]["udf_status"] == "APPROVED"


def test_rest_rollback_from_local_only_env(monkeypatch):
    """Setting mode back to Rest restores paid sync path (rollback)."""
    monkeypatch.setenv("SQL_ACCOUNTING_PR_AWARD_SYNC_MODE", "Rest")
    settings = load_sql_accounting_pr_award_sync_settings()
    assert settings.is_rest is True


def test_sdk_award_path_still_blocked_when_not_local_only(monkeypatch):
    from api.clients import SqlAccountingApiError

    payload = _install_local_body(monkeypatch)
    monkeypatch.setattr(
        "api.config.sql_accounting_pr_award_sync.load_sql_accounting_pr_award_sync_settings",
        lambda: SqlAccountingPrAwardSyncSettings(mode=AWARD_SYNC_REST),
    )
    monkeypatch.setattr(
        "api.config.sql_accounting_pr_write.load_sql_accounting_pr_write_settings",
        lambda: SqlAccountingPurchaseRequestWriteSettings(
            provider=PROVIDER_SDK, block_rest_http=False, cud_enabled=True
        ),
    )
    rest_hits = {"n": 0}

    def _boom_rest(*_a, **_k):
        rest_hits["n"] += 1
        raise AssertionError("REST must not run")

    monkeypatch.setattr("utils.procurement_sql_api_sync.SqlAccountingApiClient", _boom_rest)

    with pytest.raises(SqlAccountingApiError, match="award sync blocked"):
        sync_purchase_request_sql_api_after_awards(80, keep_dtlkeys={4, 5})
    assert rest_hits["n"] == 0
    assert payload["sdsdocdetail"][0]["udf_supcode"] == "400-L0014"


def test_missing_dockey_skipped():
    result = sync_purchase_request_sql_api_after_awards(0)
    assert result.get("skipped") is True
    assert result.get("reason") == "missing request dockey"


def test_duplicate_request_local_only_is_idempotent_skip_of_paid_path(monkeypatch):
    """Calling sync twice in LocalOnly never hits REST (duplicate/safe retry)."""
    _install_local_body(monkeypatch)
    monkeypatch.setattr(
        "api.config.sql_accounting_pr_award_sync.load_sql_accounting_pr_award_sync_settings",
        lambda: SqlAccountingPrAwardSyncSettings(mode=AWARD_SYNC_LOCAL_ONLY),
    )
    monkeypatch.setattr(
        "api.config.sql_accounting_pr_award_sync.verify_local_only_company_identity",
        lambda: type(
            "C",
            (),
            {"ok": True, "local_database": "ACC-ANOZ.FDB", "reason": "ok"},
        )(),
    )
    rest_hits = {"n": 0}

    def _boom(*_a, **_k):
        rest_hits["n"] += 1
        raise AssertionError("REST")

    monkeypatch.setattr("utils.procurement_sql_api_sync.SqlAccountingApiClient", _boom)
    first = sync_purchase_request_sql_api_after_awards(80, keep_dtlkeys={4, 5, 6})
    second = sync_purchase_request_sql_api_after_awards(80, keep_dtlkeys={4, 5, 6})
    assert first["mode"] == "localOnly"
    assert second["mode"] == "localOnly"
    assert rest_hits["n"] == 0
