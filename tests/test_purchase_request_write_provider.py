"""Mock tests for Purchase Request Rest|Sdk provider switching (Phase 2.4b)."""
from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from api.adapters.sqlacc_purchase_request_writer import (
    COM_EXPOSES_AWARD_SUPPLIER_UDFS,
    assert_award_supplier_udfs_preservable,
    assert_purchase_request_mapping_supported,
    collect_unresolved_mappings,
    create_purchase_request_via_com,
    payload_award_supplier_udf_issues,
    update_purchase_request_via_com,
)
from api.clients import SqlAccountingApiError
from api.config.sql_acc_sdk import SqlAccSdkSettings
from api.config.sql_accounting_pr_write import (
    PROVIDER_REST,
    PROVIDER_SDK,
    SqlAccountingPurchaseRequestWriteSettings,
    load_sql_accounting_pr_write_settings,
)
from api.services.purchase_request_write import (
    PurchaseRequestConfigurationError,
    RestPurchaseRequestWriteAdapter,
    SdkPurchaseRequestWriteAdapter,
    SelectingPurchaseRequestWriteAdapter,
)


DOC = "PR-26110099"


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


def _line(**extra) -> dict[str, Any]:
    base = {
        "itemcode": "AL6061-T6 ANOZ PL12.0",
        "description": "Plate",
        "qty": "1.00",
        "uom": "KGS",
        "unitprice": "3.00",
        "amount": "3.00",
        "location": "----",
        "project": "----",
        "udf_mtype": "AL",
    }
    base.update(extra)
    return base


def _payload(**extra) -> dict[str, Any]:
    base = {
        "docno": DOC,
        "code": "----",
        "companyname": "",
        "currencycode": "----",
        "currencyrate": "1",
        "shipper": "----",
        "status": 1,
        "udf_status": "APPROVED",
        "sdsdocdetail": [_line()],
    }
    base.update(extra)
    return base


def _award_payload() -> dict[str, Any]:
    return _payload(
        sdsdocdetail=[
            _line(udf_supcode="400-L0014", udf_supname="LYH yong", unitprice="3.00"),
        ]
    )


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
) -> tuple[SelectingPurchaseRequestWriteAdapter, list, _CountingSession]:
    calls = rest_calls if rest_calls is not None else []

    def _rest_attempt():
        calls.append("rest")
        return {
            "success": True,
            "dockey": 87,
            "docno": DOC,
            "message": "ok",
            "write_provider": PROVIDER_REST,
        }

    sess = session or _CountingSession()
    selecting = SelectingPurchaseRequestWriteAdapter(
        SqlAccountingPurchaseRequestWriteSettings(
            provider=provider,
            block_rest_http=block_rest,
            cud_enabled=cud_enabled,
        ),
        RestPurchaseRequestWriteAdapter(_rest_attempt),
        SdkPurchaseRequestWriteAdapter(
            sdk_settings=_sdk_settings(allow=sdk_allow),
            session_manager=sess,  # type: ignore[arg-type]
            cud_enabled=cud_enabled,
            create_writer=create_writer
            or (
                lambda app, payload: {
                    "dockey": 99,
                    "docno": payload.get("docno"),
                    "message": "Purchase request created successfully",
                    "provider": "Sdk",
                }
            ),
            update_writer=update_writer
            or (
                lambda app, payload, dockey=0: {
                    "dockey": dockey or 99,
                    "docno": payload.get("docno"),
                    "message": "Purchase request updated successfully",
                    "provider": "Sdk",
                }
            ),
        ),
    )
    return selecting, calls, sess


def test_default_provider_is_rest(monkeypatch):
    monkeypatch.delenv("SQL_ACCOUNTING_PR_WRITE_PROVIDER", raising=False)
    monkeypatch.delenv("SQLACC_SDK_PR_CUD_ENABLED", raising=False)
    settings = load_sql_accounting_pr_write_settings()
    assert settings.provider == PROVIDER_REST
    assert settings.cud_enabled is False


def test_mapping_accepts_verified_fields():
    assert collect_unresolved_mappings(_payload()) == []
    assert_purchase_request_mapping_supported(_payload())


def test_unsupported_udf_stdprice_is_reported():
    payload = _payload(sdsdocdetail=[_line(udf_stdprice="12.50")])
    issues = collect_unresolved_mappings(payload)
    assert any("udf_stdprice" in i for i in issues)
    with pytest.raises(SqlAccountingApiError, match="udf_stdprice"):
        assert_purchase_request_mapping_supported(payload)


def test_award_supplier_udfs_blocked_when_com_unexposed():
    assert COM_EXPOSES_AWARD_SUPPLIER_UDFS is False
    issues = payload_award_supplier_udf_issues(_award_payload())
    assert issues
    assert any("udf_supcode" in i for i in issues)
    with pytest.raises(SqlAccountingApiError, match="award sync blocked"):
        assert_award_supplier_udfs_preservable(_award_payload())
    with pytest.raises(SqlAccountingApiError, match="udf_supcode|award"):
        assert_purchase_request_mapping_supported(_award_payload())


def test_award_udfs_allowed_when_com_flag_enabled(monkeypatch):
    monkeypatch.setattr(
        "api.adapters.sqlacc_purchase_request_writer.COM_EXPOSES_AWARD_SUPPLIER_UDFS",
        True,
    )
    assert payload_award_supplier_udf_issues(_award_payload()) == []
    assert_award_supplier_udfs_preservable(_award_payload())


def test_rest_provider_uses_rest_not_sdk():
    selecting, calls, sess = _selecting(provider=PROVIDER_REST)
    result = selecting.write_purchase_request(_payload(), is_update=False, dockey=0)
    assert result["write_provider"] == PROVIDER_REST
    assert calls == ["rest"]
    assert sess.calls == 0


def test_sdk_provider_uses_session_not_rest():
    selecting, calls, sess = _selecting(provider=PROVIDER_SDK)
    result = selecting.write_purchase_request(_payload(), is_update=False, dockey=0)
    assert result["write_provider"] == PROVIDER_SDK
    assert result["dockey"] == 99
    assert sess.calls == 1
    assert calls == []


def test_sdk_update_path_uses_update_writer():
    seen: dict[str, Any] = {}

    def _upd(app, payload, dockey=0):
        seen["dockey"] = dockey
        return {"dockey": dockey, "docno": payload["docno"], "message": "updated", "provider": "Sdk"}

    selecting, calls, sess = _selecting(provider=PROVIDER_SDK, update_writer=_upd)
    result = selecting.write_purchase_request(_payload(), is_update=True, dockey=87)
    assert result["dockey"] == 87
    assert seen["dockey"] == 87
    assert calls == []
    assert sess.calls == 1


def test_sdk_failure_does_not_fallback_to_rest():
    selecting, calls, sess = _selecting(
        provider=PROVIDER_SDK,
        session=_CountingSession(fail=True),
    )
    with pytest.raises(SqlAccountingApiError, match="SDK boom"):
        selecting.write_purchase_request(_payload(), is_update=False, dockey=0)
    assert calls == []
    assert sess.calls == 1


def test_block_rest_http_refuses_rest():
    selecting, calls, sess = _selecting(provider=PROVIDER_REST, block_rest=True)
    with pytest.raises(PurchaseRequestConfigurationError, match="BLOCK_REST_HTTP"):
        selecting.write_purchase_request(_payload(), is_update=False, dockey=0)
    assert calls == []
    assert sess.calls == 0


def test_sdk_refuses_without_allow_live_com():
    selecting, calls, sess = _selecting(provider=PROVIDER_SDK, sdk_allow=False)
    with pytest.raises(PurchaseRequestConfigurationError, match="ALLOW_LIVE_COM"):
        selecting.write_purchase_request(_payload(), is_update=False, dockey=0)
    assert calls == []


def test_sdk_refuses_without_cud_enabled():
    selecting, calls, sess = _selecting(provider=PROVIDER_SDK, cud_enabled=False)
    with pytest.raises(PurchaseRequestConfigurationError, match="PR_CUD_ENABLED"):
        selecting.write_purchase_request(_payload(), is_update=False, dockey=0)
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
            selecting.write_purchase_request(_payload(), is_update=False, dockey=0)
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


class _FakeField:
    def __init__(self, name: str) -> None:
        self.FieldName = name
        self.AsString = ""


class _FakeFields:
    def __init__(self, names: list[str]) -> None:
        self._fields = {n: _FakeField(n) for n in names}

    @property
    def Count(self) -> int:
        return len(self._fields)

    def Items(self, idx: int) -> _FakeField:
        return list(self._fields.values())[idx]

    def FindField(self, name: str) -> _FakeField | None:
        return self._fields.get(name)


class _FakeDataSet:
    def __init__(self, names: list[str]) -> None:
        self.Fields = _FakeFields(names)
        self.RecordCount = 0
        self._rows: list[dict[str, str]] = []

    def Append(self) -> None:
        self._rows.append({})
        self.RecordCount = len(self._rows)

    def Post(self) -> None:
        return None

    def Last(self) -> None:
        return None

    def Delete(self) -> None:
        if self._rows:
            self._rows.pop()
            self.RecordCount = len(self._rows)


class _FakeParams:
    def __init__(self) -> None:
        self._vals: dict[str, Any] = {}

    def Find(self, name: str) -> Any:
        class _P:
            def __init__(self, store: dict[str, Any], key: str) -> None:
                self._store = store
                self._key = key

            @property
            def Value(self) -> Any:
                return self._store.get(self._key)

            @Value.setter
            def Value(self, v: Any) -> None:
                self._store[self._key] = v

        return _P(self._vals, name)


class _FakeBiz:
    def __init__(self, *, existing_docno: str | None = None) -> None:
        self.existing_docno = existing_docno
        self.Params = _FakeParams()
        self.DataSets = self
        self._main = _FakeDataSet(
            ["DOCKEY", "DOCNO", "CODE", "COMPANYNAME", "CURRENCYCODE", "SHIPPER", "STATUS", "UDF_Status"]
        )
        self._detail = _FakeDataSet(
            ["DTLKEY", "DOCKEY", "SEQ", "ITEMCODE", "QTY", "UOM", "UNITPRICE", "AMOUNT", "LOCATION", "PROJECT", "UDF_MType"]
        )
        self.saved = False
        self.opened = False
        self.edited = False

    def Find(self, name: str) -> Any:
        if name == "MainDataSet":
            return self._main
        if name == "cdsDocDetail":
            return self._detail
        raise KeyError(name)

    def FindKeyByRef(self, field: str, doc_no: str) -> Any:
        if self.existing_docno and doc_no == self.existing_docno:
            return 87
        return None

    def New(self) -> None:
        return None

    def Open(self) -> None:
        self.opened = True

    def Edit(self) -> None:
        self.edited = True

    def Save(self) -> None:
        self.saved = True

    def Close(self) -> None:
        return None


class _FakeBizObjects:
    def __init__(self, biz: _FakeBiz) -> None:
        self._biz = biz

    def Find(self, name: str) -> _FakeBiz:
        assert name == "PH_PQ"
        return self._biz


class _FakeApp:
    def __init__(self, biz: _FakeBiz, *, persist_docno: str | None = None) -> None:
        self.BizObjects = _FakeBizObjects(biz)
        self._persist_docno = persist_docno
        self.DBManager = self

    def NewDataSet(self, sql: str) -> Any:
        class _RowSet:
            def __init__(self, row: dict[str, str] | None) -> None:
                self.RecordCount = 1 if row else 0
                fields = _FakeFields(list(row.keys()) if row else [])
                if row:
                    for name, value in row.items():
                        fields._fields[name].AsString = value
                self.Fields = fields
                self.Eof = True

            def First(self) -> None:
                return None

        if self._persist_docno and "FROM PH_PQ" in sql and self._persist_docno in sql:
            return _RowSet(
                {
                    "DOCKEY": "99",
                    "DOCNO": self._persist_docno,
                    "CODE": "----",
                    "UPDATECOUNT": "1",
                }
            )
        return _RowSet(None)


def test_create_via_com_duplicate_docno_blocked():
    biz = _FakeBiz(existing_docno=DOC)
    app = _FakeApp(biz)
    with pytest.raises(SqlAccountingApiError, match="already exists"):
        create_purchase_request_via_com(app, _payload())
    assert biz.saved is False


def test_create_via_com_maps_and_saves():
    biz = _FakeBiz()
    app = _FakeApp(biz, persist_docno=DOC)
    result = create_purchase_request_via_com(app, _payload())
    assert biz.saved is True
    assert result["docno"] == DOC
    assert result["dockey"] == 99
    assert result["provider"] == "Sdk"


def test_update_via_com_requires_existing():
    biz = _FakeBiz()
    app = _FakeApp(biz)
    with pytest.raises(SqlAccountingApiError, match="not found"):
        update_purchase_request_via_com(app, _payload(), dockey=87)


def test_update_via_com_opens_edits_saves():
    biz = _FakeBiz(existing_docno=DOC)
    app = _FakeApp(biz, persist_docno=DOC)
    result = update_purchase_request_via_com(app, _payload(), dockey=87)
    assert biz.opened and biz.edited and biz.saved
    assert result["dockey"] == 99


def test_create_via_com_blocks_award_udfs_before_save():
    biz = _FakeBiz()
    app = _FakeApp(biz, persist_docno=DOC)
    with pytest.raises(SqlAccountingApiError, match="award sync blocked"):
        create_purchase_request_via_com(app, _award_payload())
    assert biz.saved is False


def test_sync_after_awards_rest_default(monkeypatch):
    from utils import procurement_sql_api_sync as sync
    import api.config.sql_accounting_pr_award_sync as award_cfg
    import api.config.sql_accounting_pr_write as pr_cfg
    from api.config.sql_accounting_pr_award_sync import (
        AWARD_SYNC_REST,
        SqlAccountingPrAwardSyncSettings as AwardSettings,
    )

    monkeypatch.setattr(
        award_cfg,
        "load_sql_accounting_pr_award_sync_settings",
        lambda: AwardSettings(mode=AWARD_SYNC_REST),
    )
    monkeypatch.setattr(
        sync,
        "load_sql_accounting_api_settings",
        lambda: type(
            "S",
            (),
            {
                "access_key": "ak",
                "secret_key": "sk",
                "timeout_seconds": 10.0,
                "host": "api.example",
                "use_tls": True,
            },
        )(),
    )
    monkeypatch.setattr(
        pr_cfg,
        "load_sql_accounting_pr_write_settings",
        lambda: SqlAccountingPurchaseRequestWriteSettings(
            provider=PROVIDER_REST, block_rest_http=False, cud_enabled=False
        ),
    )
    monkeypatch.setattr(sync, "_all_local_pqdtl_keys", lambda dockey: {4})
    monkeypatch.setattr(
        sync,
        "_build_purchaserequest_body_from_local",
        lambda dockey, keep_dtlkeys=None: (
            DOC,
            _award_payload() | {"dockey": dockey, "docno": DOC},
        ),
    )

    class Client:
        def post_json(self, url, payload, timeout_seconds=None):
            return 200, {"dockey": 80, "docno": DOC}, "{}"

        def get_json(self, *a, **k):
            return 404, None, ""

    monkeypatch.setattr(sync, "SqlAccountingApiClient", lambda settings: Client())
    monkeypatch.setattr(sync, "_get_document", lambda *a, **k: None)
    monkeypatch.setattr(sync, "_api_root_url", lambda *a, **k: "https://api.example/purchaserequest")

    result = sync.sync_purchase_request_sql_api_after_awards(80, keep_dtlkeys={4})
    assert result["synced"] is True
    assert result["mode"] == "post"
    assert result["write_provider"] == PROVIDER_REST


def test_sync_after_awards_sdk_blocks_award_udfs_before_com(monkeypatch):
    from utils import procurement_sql_api_sync as sync
    import api.config.sql_accounting_pr_award_sync as award_cfg
    import api.config.sql_accounting_pr_write as pr_cfg
    from api.config.sql_accounting_pr_award_sync import (
        AWARD_SYNC_REST,
        SqlAccountingPrAwardSyncSettings as AwardSettings,
    )

    monkeypatch.setattr(
        award_cfg,
        "load_sql_accounting_pr_award_sync_settings",
        lambda: AwardSettings(mode=AWARD_SYNC_REST),
    )
    monkeypatch.setattr(
        pr_cfg,
        "load_sql_accounting_pr_write_settings",
        lambda: SqlAccountingPurchaseRequestWriteSettings(
            provider=PROVIDER_SDK, block_rest_http=False, cud_enabled=True
        ),
    )
    monkeypatch.setattr(sync, "_all_local_pqdtl_keys", lambda dockey: {4})
    monkeypatch.setattr(
        sync,
        "_build_purchaserequest_body_from_local",
        lambda dockey, keep_dtlkeys=None: (DOC, _award_payload() | {"dockey": dockey, "docno": DOC}),
    )

    rest_called = {"n": 0}

    def _boom_rest(*a, **k):
        rest_called["n"] += 1
        raise AssertionError("REST must not run when Sdk blocks awards")

    monkeypatch.setattr(sync, "SqlAccountingApiClient", _boom_rest)
    monkeypatch.setattr(sync, "_get_document", _boom_rest)

    with pytest.raises(SqlAccountingApiError, match="award sync blocked"):
        sync.sync_purchase_request_sql_api_after_awards(80, keep_dtlkeys={4})
    assert rest_called["n"] == 0


def test_sync_after_awards_sdk_no_rest_fallback_on_config_error(monkeypatch):
    from utils import procurement_sql_api_sync as sync
    import api.config.sql_accounting_pr_award_sync as award_cfg
    import api.config.sql_accounting_pr_write as pr_cfg
    from api.config.sql_accounting_pr_award_sync import (
        AWARD_SYNC_REST,
        SqlAccountingPrAwardSyncSettings as AwardSettings,
    )

    monkeypatch.setattr(
        award_cfg,
        "load_sql_accounting_pr_award_sync_settings",
        lambda: AwardSettings(mode=AWARD_SYNC_REST),
    )
    monkeypatch.setattr(
        pr_cfg,
        "load_sql_accounting_pr_write_settings",
        lambda: SqlAccountingPurchaseRequestWriteSettings(
            provider=PROVIDER_SDK, block_rest_http=False, cud_enabled=False
        ),
    )
    monkeypatch.setattr(sync, "_all_local_pqdtl_keys", lambda dockey: {4})
    # No award UDFs so gate passes; CUD gate then blocks before Save.
    monkeypatch.setattr(
        sync,
        "_build_purchaserequest_body_from_local",
        lambda dockey, keep_dtlkeys=None: (DOC, _payload() | {"dockey": dockey, "docno": DOC}),
    )

    class _Mgr:
        def run(self, action, *, timeout_seconds=None):
            class _App:
                class BizObjects:
                    @staticmethod
                    def Find(name):
                        return _FakeBiz()

            return action(_App())

    monkeypatch.setattr(
        "api.adapters.sqlacc_session.get_sqlacc_session_manager",
        lambda: _Mgr(),
    )
    monkeypatch.setattr(
        "api.services.purchase_request_write.get_sqlacc_session_manager",
        lambda: _Mgr(),
    )
    monkeypatch.setattr(
        "api.services.purchase_request_write.load_sql_acc_sdk_settings",
        lambda: _sdk_settings(allow=True),
    )

    rest_called = {"n": 0}
    monkeypatch.setattr(
        sync,
        "SqlAccountingApiClient",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no REST")),
    )

    with pytest.raises(PurchaseRequestConfigurationError, match="PR_CUD_ENABLED"):
        sync.sync_purchase_request_sql_api_after_awards(80, keep_dtlkeys={4})
    assert rest_called["n"] == 0
