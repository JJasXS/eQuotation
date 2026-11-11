"""Mock tests for Sales Quotation Rest|Sdk provider switching (Phase 2.3b)."""
from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from api.adapters.sqlacc_quotation_writer import (
    assert_quotation_mapping_supported,
    collect_unresolved_mappings,
)
from api.clients import SqlAccountingApiError
from api.config.sql_acc_sdk import SqlAccSdkSettings
from api.config.sql_accounting_quotation_write import (
    PROVIDER_REST,
    PROVIDER_SDK,
    SqlAccountingQuotationWriteSettings,
)
from api.services.quotation_write import (
    QuotationConfigurationError,
    RestQuotationWriteAdapter,
    SdkQuotationWriteAdapter,
    SelectingQuotationWriteAdapter,
)
from utils.quotation_api import create_or_update_quotation


CUSTOMER = "300-C0001"
DOC = "QT-80001"
CREATE_URL = "https://api.example/salesquotation"


def _sdk_settings(*, allow: bool = True) -> SqlAccSdkSettings:
    return SqlAccSdkSettings(
        prog_id="SQLAcc.BizApp",
        allow_live_com=allow,
        dcf_path=r"C:\Share\SQLACC.DCF",
        database_file="ACC-ANOZ.FDB",
        username="ADMIN",
        password="secret",
        logout_after_use=True,
        customer_control_account="",
        login_timeout_seconds=30.0,
        session_idle_seconds=300.0,
    )


def _payload(**extra) -> dict[str, Any]:
    base = {
        "docno": DOC,
        "code": CUSTOMER,
        "companyname": "Example Co",
        "currencycode": "MYR",
        "currencyrate": "1.00",
        "status": 0,
        "cancelled": False,
        "udf_status": "PENDING",
        "sdsdocdetail": [
            {
                "itemcode": "ITEM-1",
                "description": "Line",
                "qty": "1.00",
                "uom": "PCS",
                "unitprice": "10.00",
                "amount": "10.00",
                "udf_mtype": "Sheet",
            }
        ],
    }
    base.update(extra)
    return base


class _CountingSession:
    def __init__(self, *, fail: bool = False, hold_seconds: float = 0.0) -> None:
        self.calls = 0
        self.active = 0
        self.max_active = 0
        self._gate = threading.Lock()
        self._stats = threading.Lock()
        self.fail = fail
        self.hold_seconds = hold_seconds

    def run(self, action, *, timeout_seconds=None):
        with self._gate:
            with self._stats:
                self.calls += 1
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            try:
                if self.hold_seconds:
                    time.sleep(self.hold_seconds)
                if self.fail:
                    raise SqlAccountingApiError("SDK boom", status_code=502)

                class _App:
                    pass

                return action(_App())
            finally:
                with self._stats:
                    self.active -= 1


def _selecting(
    *,
    provider: str,
    rest_calls: list | None = None,
    session: _CountingSession | None = None,
    block_rest: bool = False,
    cud_enabled: bool = True,
    sdk_allow: bool = True,
    create_writer=None,
    update_writer=None,
) -> tuple[SelectingQuotationWriteAdapter, list, _CountingSession]:
    calls = rest_calls if rest_calls is not None else []

    def _rest_attempt():
        calls.append("rest")
        return {
            "success": True,
            "dockey": 7,
            "docno": DOC,
            "message": "Quotation created successfully",
            "write_provider": PROVIDER_REST,
        }

    sess = session or _CountingSession()
    selecting = SelectingQuotationWriteAdapter(
        SqlAccountingQuotationWriteSettings(
            provider=provider,
            block_rest_http=block_rest,
            cud_enabled=cud_enabled,
        ),
        RestQuotationWriteAdapter(_rest_attempt),
        SdkQuotationWriteAdapter(
            sdk_settings=_sdk_settings(allow=sdk_allow),
            session_manager=sess,  # type: ignore[arg-type]
            cud_enabled=cud_enabled,
            create_writer=create_writer
            or (
                lambda app, payload: {
                    "dockey": 11,
                    "docno": payload.get("docno"),
                    "message": "Quotation created successfully",
                    "provider": "Sdk",
                }
            ),
            update_writer=update_writer
            or (
                lambda app, payload, dockey=0: {
                    "dockey": dockey or 11,
                    "docno": payload.get("docno"),
                    "message": "Quotation updated successfully",
                    "provider": "Sdk",
                }
            ),
        ),
    )
    return selecting, calls, sess


def test_mapping_accepts_verified_fields():
    assert collect_unresolved_mappings(_payload()) == []
    assert_quotation_mapping_supported(_payload())


def test_unsupported_udf_eprice_is_reported():
    payload = _payload()
    payload["sdsdocdetail"][0]["udf_eprice"] = "12.50"
    issues = collect_unresolved_mappings(payload)
    assert any("udf_eprice" in i for i in issues)
    with pytest.raises(SqlAccountingApiError, match="udf_eprice"):
        assert_quotation_mapping_supported(payload)


def test_unsupported_nextdocno_is_reported():
    payload = _payload(nextdocno="QT-99999")
    issues = collect_unresolved_mappings(payload)
    assert any("nextdocno" in i for i in issues)


def test_zero_udf_eprice_is_ignored():
    payload = _payload()
    payload["sdsdocdetail"][0]["udf_eprice"] = "0.00"
    assert collect_unresolved_mappings(payload) == []


def test_rest_provider_uses_rest_not_sdk():
    selecting, calls, sess = _selecting(provider=PROVIDER_REST)
    result = selecting.write_quotation(_payload(), is_update=False, dockey=0)
    assert result["write_provider"] == PROVIDER_REST
    assert calls == ["rest"]
    assert sess.calls == 0


def test_sdk_provider_uses_session_not_rest():
    selecting, calls, sess = _selecting(provider=PROVIDER_SDK)
    result = selecting.write_quotation(_payload(), is_update=False, dockey=0)
    assert result["write_provider"] == PROVIDER_SDK
    assert result["dockey"] == 11
    assert sess.calls == 1
    assert calls == []


def test_sdk_update_path_uses_update_writer():
    seen = {}

    def _upd(app, payload, dockey=0):
        seen["dockey"] = dockey
        return {"dockey": dockey, "docno": payload["docno"], "message": "updated", "provider": "Sdk"}

    selecting, calls, sess = _selecting(provider=PROVIDER_SDK, update_writer=_upd)
    result = selecting.write_quotation(_payload(), is_update=True, dockey=175)
    assert result["dockey"] == 175
    assert seen["dockey"] == 175
    assert calls == []
    assert sess.calls == 1


def test_sdk_failure_does_not_fallback_to_rest():
    selecting, calls, sess = _selecting(
        provider=PROVIDER_SDK,
        session=_CountingSession(fail=True),
    )
    with pytest.raises(SqlAccountingApiError, match="SDK boom"):
        selecting.write_quotation(_payload(), is_update=False, dockey=0)
    assert calls == []
    assert sess.calls == 1


def test_block_rest_http_refuses_rest():
    selecting, calls, sess = _selecting(provider=PROVIDER_REST, block_rest=True)
    with pytest.raises(QuotationConfigurationError, match="BLOCK_REST_HTTP"):
        selecting.write_quotation(_payload(), is_update=False, dockey=0)
    assert calls == []
    assert sess.calls == 0


def test_sdk_refuses_without_allow_live_com():
    selecting, calls, sess = _selecting(provider=PROVIDER_SDK, sdk_allow=False)
    with pytest.raises(QuotationConfigurationError, match="ALLOW_LIVE_COM"):
        selecting.write_quotation(_payload(), is_update=False, dockey=0)
    assert calls == []


def test_sdk_refuses_without_cud_enabled():
    selecting, calls, sess = _selecting(provider=PROVIDER_SDK, cud_enabled=False)
    with pytest.raises(QuotationConfigurationError, match="QUOTATION_CUD_ENABLED"):
        selecting.write_quotation(_payload(), is_update=False, dockey=0)
    assert calls == []
    assert sess.calls == 0


def test_sdk_concurrency_serialized_on_session_gate():
    selecting, calls, sess = _selecting(
        provider=PROVIDER_SDK,
        session=_CountingSession(hold_seconds=0.05),
    )
    errors: list[BaseException] = []

    def _worker():
        try:
            selecting.write_quotation(_payload(), is_update=False, dockey=0)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert sess.calls == 4
    assert sess.max_active == 1
    assert calls == []


class _Settings:
    access_key = "test-key"
    secret_key = "test-secret"
    timeout_seconds = 12.0
    quotation_create_path = "/salesquotation"
    dry_run = False

    def resolved_quotation_create_url(self):
        return CREATE_URL

    def resolved_quotation_update_url(self, dockey):
        return f"{CREATE_URL}/{int(dockey)}"


def _install_rest_orchestration(monkeypatch, client, *, write_settings=None, dry_run=False):
    settings = _Settings()
    settings.dry_run = dry_run
    monkeypatch.setattr("utils.quotation_api.load_sql_accounting_api_settings", lambda: settings)
    monkeypatch.setattr(
        "utils.quotation_api.load_sql_accounting_quotation_write_settings",
        lambda: write_settings
        or SqlAccountingQuotationWriteSettings(
            provider=PROVIDER_REST,
            block_rest_http=False,
            cud_enabled=False,
        ),
    )
    monkeypatch.setattr("utils.quotation_api.SqlAccountingApiClient", lambda _settings: client)
    monkeypatch.setattr(
        "utils.quotation_api._build_salesquotation_payload",
        lambda customer_code, data, doc_no: {
            "docno": doc_no,
            "code": customer_code,
            "sdsdocdetail": [{"itemcode": "ITEM-1", "qty": "1"}],
        },
    )
    monkeypatch.setattr("utils.quotation_api._local_precheck_quotation", lambda *a, **k: None)
    monkeypatch.setattr(
        "utils.quotation_api._read_qt_sequences_from_db",
        lambda limit=2000: (80000, {80000}, None),
    )
    monkeypatch.setattr("utils.quotation_api._next_qt_docno_candidate", lambda *a, **k: DOC)


def test_create_or_update_rest_default_posts(monkeypatch):
    class Client:
        posts = []

        def post_json(self, url, payload, timeout_seconds=None):
            self.posts.append(url)
            return 200, {"dockey": 7, "docno": DOC}, "{}"

    client = Client()
    _install_rest_orchestration(monkeypatch, client)
    result = create_or_update_quotation(
        "http://local",
        CUSTOMER,
        {"items": [{"product": "x", "qty": 1, "price": 1}]},
    )
    assert result["success"] is True
    assert result["write_provider"] == PROVIDER_REST
    assert client.posts == [CREATE_URL]


def test_create_or_update_dry_run_skips_rest_only(monkeypatch):
    class Client:
        posts = []

        def post_json(self, *a, **k):
            self.posts.append(1)
            return 200, {}, "{}"

    client = Client()
    _install_rest_orchestration(monkeypatch, client, dry_run=True)
    result = create_or_update_quotation(
        "http://local",
        CUSTOMER,
        {"items": [{"product": "x", "qty": 1, "price": 1}]},
    )
    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["write_provider"] == PROVIDER_REST
    assert client.posts == []

    # SQL_API_DRY_RUN must not block Sdk (COM has AllowLiveCom + CUD gates).
    sdk_settings = SqlAccountingQuotationWriteSettings(
        provider=PROVIDER_SDK,
        block_rest_http=False,
        cud_enabled=True,
    )
    _install_rest_orchestration(monkeypatch, client, write_settings=sdk_settings, dry_run=True)

    class _SdkOk:
        def __init__(self, *a, **k):
            pass

        def write_quotation(self, payload, *, is_update, dockey):
            return {
                "success": True,
                "dockey": 5,
                "docno": payload.get("docno") or DOC,
                "message": "ok",
                "write_provider": PROVIDER_SDK,
            }

    monkeypatch.setattr("utils.quotation_api.SdkQuotationWriteAdapter", _SdkOk)
    result2 = create_or_update_quotation(
        "http://local",
        CUSTOMER,
        {"items": [{"product": "x", "qty": 1, "price": 1}]},
    )
    assert result2["success"] is True
    assert result2.get("dry_run") is not True
    assert result2["write_provider"] == PROVIDER_SDK
    assert client.posts == []


def test_sdk_save_does_not_require_rest_api_keys(monkeypatch):
    class Client:
        posts = []

        def post_json(self, *a, **k):
            self.posts.append(1)
            raise AssertionError("REST must not be called for Sdk quotation write")

    class _Settings:
        access_key = ""
        secret_key = ""
        timeout_seconds = 12.0
        quotation_create_path = "/salesquotation"
        dry_run = False

        def resolved_quotation_create_url(self):
            return CREATE_URL

        def resolved_quotation_update_url(self, dockey):
            return f"{CREATE_URL}/{int(dockey)}"

    monkeypatch.setattr("utils.quotation_api.load_sql_accounting_api_settings", lambda: _Settings())
    monkeypatch.setattr(
        "utils.quotation_api.load_sql_accounting_quotation_write_settings",
        lambda: SqlAccountingQuotationWriteSettings(
            provider=PROVIDER_SDK,
            block_rest_http=False,
            cud_enabled=True,
        ),
    )
    monkeypatch.setattr("utils.quotation_api.SqlAccountingApiClient", lambda _settings: Client())
    monkeypatch.setattr(
        "utils.quotation_api._build_salesquotation_payload",
        lambda customer_code, data, doc_no: {
            "docno": doc_no,
            "code": customer_code,
            "sdsdocdetail": [{"itemcode": "ITEM-1", "qty": "1"}],
        },
    )
    monkeypatch.setattr("utils.quotation_api._local_precheck_quotation", lambda *a, **k: None)
    monkeypatch.setattr(
        "utils.quotation_api._read_qt_sequences_from_db",
        lambda limit=2000: (80000, set(), None),
    )
    monkeypatch.setattr("utils.quotation_api._next_qt_docno_candidate", lambda *a, **k: DOC)

    class _SdkOk:
        def __init__(self, *a, **k):
            pass

        def write_quotation(self, payload, *, is_update, dockey):
            return {
                "success": True,
                "dockey": 42,
                "docno": payload.get("docno"),
                "message": "Quotation created successfully",
                "write_provider": PROVIDER_SDK,
            }

    monkeypatch.setattr("utils.quotation_api.SdkQuotationWriteAdapter", _SdkOk)
    result = create_or_update_quotation(
        "http://local",
        CUSTOMER,
        {"items": [{"product": "x", "qty": 1, "price": 1}]},
    )
    assert result["success"] is True
    assert result["write_provider"] == PROVIDER_SDK
    assert result["dockey"] == 42


def test_rest_save_still_requires_api_keys(monkeypatch):
    class _Settings:
        access_key = ""
        secret_key = ""
        timeout_seconds = 12.0
        quotation_create_path = "/salesquotation"
        dry_run = False

    monkeypatch.setattr("utils.quotation_api.load_sql_accounting_api_settings", lambda: _Settings())
    monkeypatch.setattr(
        "utils.quotation_api.load_sql_accounting_quotation_write_settings",
        lambda: SqlAccountingQuotationWriteSettings(
            provider=PROVIDER_REST,
            block_rest_http=False,
            cud_enabled=False,
        ),
    )
    result = create_or_update_quotation(
        "http://local",
        CUSTOMER,
        {"items": [{"product": "x", "qty": 1, "price": 1}]},
    )
    assert result["success"] is False
    assert result["error"] == "SQL API keys are not configured"


def test_create_or_update_sdk_no_rest_fallback_on_failure(monkeypatch):
    class Client:
        posts = []

        def post_json(self, *a, **k):
            self.posts.append(1)
            return 200, {}, "{}"

    client = Client()
    _install_rest_orchestration(
        monkeypatch,
        client,
        write_settings=SqlAccountingQuotationWriteSettings(
            provider=PROVIDER_SDK,
            block_rest_http=False,
            cud_enabled=True,
        ),
    )

    class _Boom:
        def __init__(self, *a, **k):
            pass

        def write_quotation(self, *a, **k):
            raise SqlAccountingApiError("SDK boom", status_code=502)

    monkeypatch.setattr("utils.quotation_api.SdkQuotationWriteAdapter", _Boom)
    result = create_or_update_quotation(
        "http://local",
        CUSTOMER,
        {"items": [{"product": "x", "qty": 1, "price": 1}]},
    )
    assert result["success"] is False
    assert "SDK boom" in result["error"]
    assert result["write_provider"] == PROVIDER_SDK
    assert client.posts == []


def test_create_or_update_sdk_duplicate_docno_retries_without_rest(monkeypatch):
    class Client:
        posts = []

        def post_json(self, *a, **k):
            self.posts.append(1)
            return 200, {}, "{}"

    client = Client()
    attempts = {"n": 0}
    docs = []

    def _next(*a, **k):
        attempts["n"] += 1
        doc = f"QT-8000{attempts['n']}"
        docs.append(doc)
        return doc

    _install_rest_orchestration(
        monkeypatch,
        client,
        write_settings=SqlAccountingQuotationWriteSettings(
            provider=PROVIDER_SDK,
            block_rest_http=False,
            cud_enabled=True,
        ),
    )
    monkeypatch.setattr("utils.quotation_api._next_qt_docno_candidate", _next)
    monkeypatch.setattr(
        "utils.quotation_api._read_qt_sequences_from_db",
        lambda limit=2000: (80000, set(), None),
    )

    state = {"n": 0}

    class _DupThenOk:
        def __init__(self, *a, **k):
            pass

        def write_quotation(self, payload, *, is_update, dockey):
            state["n"] += 1
            if state["n"] == 1:
                raise SqlAccountingApiError(
                    f"Quotation DOCNO '{payload.get('docno')}' already exists in SL_QT (duplicate DocNo).",
                    status_code=422,
                )
            return {
                "success": True,
                "dockey": 99,
                "docno": payload.get("docno"),
                "message": "ok",
                "write_provider": PROVIDER_SDK,
            }

    monkeypatch.setattr("utils.quotation_api.SdkQuotationWriteAdapter", _DupThenOk)
    result = create_or_update_quotation(
        "http://local",
        CUSTOMER,
        {"items": [{"product": "x", "qty": 1, "price": 1}]},
    )
    assert result["success"] is True
    assert result["write_provider"] == PROVIDER_SDK
    assert client.posts == []
    assert len(docs) >= 2


def test_numbering_band_excludes_book_style_qt26100001():
    from utils.quotation_api import _QT_DOCNO_RE

    assert _QT_DOCNO_RE.match("QT-80000")
    assert _QT_DOCNO_RE.match("QT-99999")
    assert _QT_DOCNO_RE.match("QT-26100001") is None


def test_create_or_update_block_rest_without_sdk(monkeypatch):
    class Client:
        posts = []

        def post_json(self, *a, **k):
            self.posts.append(1)
            return 200, {}, "{}"

    client = Client()
    _install_rest_orchestration(
        monkeypatch,
        client,
        write_settings=SqlAccountingQuotationWriteSettings(
            provider=PROVIDER_REST,
            block_rest_http=True,
            cud_enabled=False,
        ),
    )
    result = create_or_update_quotation(
        "http://local",
        CUSTOMER,
        {"items": [{"product": "x", "qty": 1, "price": 1}]},
    )
    assert result["success"] is False
    assert "BLOCK_REST_HTTP" in result["error"]
    assert client.posts == []
