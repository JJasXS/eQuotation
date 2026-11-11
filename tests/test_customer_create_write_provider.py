"""Mock tests for customer create Rest|Sdk provider switching (Phase 2.1)."""
from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from api.clients import SqlAccountingApiError
from api.config.sql_acc_sdk import SqlAccSdkSettings
from api.config.sql_accounting_api import SqlAccountingApiSettings
from api.config.sql_accounting_write import (
    PROVIDER_REST,
    PROVIDER_SDK,
    SqlAccountingWriteSettings,
)
from api.models import CustomerRequest
from api.services import CustomerConfigurationError, CustomerService
from api.services.customer_write import (
    RestCustomerWriteAdapter,
    SdkCustomerWriteAdapter,
    SelectingCustomerWriteAdapter,
)


def _api_settings(*, dry_run: bool = False) -> SqlAccountingApiSettings:
    return SqlAccountingApiSettings(
        access_key="ak",
        secret_key="sk",
        host="api.example.test",
        region="ap-southeast-1",
        service="sqlaccount",
        customer_create_path="/customer",
        quotation_create_path="/salesquotation",
        stock_item_list_path="",
        area_list_path="/area",
        currency_list_path="/currency",
        use_tls=True,
        timeout_seconds=12.0,
        max_retries=0,
        dry_run=dry_run,
        debug_payload=False,
    )


def _sdk_settings(*, allow: bool = True) -> SqlAccSdkSettings:
    return SqlAccSdkSettings(
        prog_id="SQLAcc.BizApp",
        allow_live_com=allow,
        dcf_path=r"C:\Share\SQLACC.DCF",
        database_file="ACC-TEST.FDB",
        username="ADMIN",
        password="secret",
        logout_after_use=True,
        customer_control_account="300-000",
        login_timeout_seconds=30.0,
        session_idle_seconds=300.0,
    )


def _request(code: str = "300-T0001") -> CustomerRequest:
    return CustomerRequest(
        code=code,
        company_name="Test Co Sdn Bhd",
        credit_term="30 Days",
        area="PPS",
        currency_code="MYR",
        email="test@example.com",
    )


class _FakeRestClient:
    def __init__(self) -> None:
        self.posts: list[tuple[str, dict[str, Any]]] = []

    def post_json(self, url, payload, timeout_seconds=None):
        self.posts.append((url, payload))
        return 200, {"code": payload.get("code"), "companyname": payload.get("companyname")}, '{"ok":true}'


class _CountingSession:
    """Mimics SqlAccSessionManager gate: one COM create at a time."""

    def __init__(self, *, fail: bool = False, duplicate: bool = False, hold_seconds: float = 0.0) -> None:
        self.calls = 0
        self.active = 0
        self.max_active = 0
        self._gate = threading.Lock()
        self._stats = threading.Lock()
        self.fail = fail
        self.duplicate = duplicate
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
                if self.duplicate:
                    raise SqlAccountingApiError(
                        "Customer code '300-T0001' already exists (duplicate CODE).",
                        status_code=422,
                    )

                class _App:
                    pass

                return action(_App())
            finally:
                with self._stats:
                    self.active -= 1


def _selecting(
    *,
    provider: str,
    rest_client: _FakeRestClient | None = None,
    session: _CountingSession | None = None,
    block_rest: bool = False,
    sdk_allow: bool = True,
    writer=None,
) -> tuple[SelectingCustomerWriteAdapter, _FakeRestClient, _CountingSession]:
    client = rest_client or _FakeRestClient()
    sess = session or _CountingSession()
    api = _api_settings()
    rest = RestCustomerWriteAdapter(api, api_client=client)
    sdk = SdkCustomerWriteAdapter(
        sdk_settings=_sdk_settings(allow=sdk_allow),
        session_manager=sess,  # type: ignore[arg-type]
        writer=writer
        or (
            lambda app, customer, control_account_override=None: {
                "code": customer.code,
                "companyName": customer.company_name,
                "controlAccount": control_account_override or "300-000",
                "message": "Created.",
                "provider": "Sdk",
            }
        ),
    )
    selecting = SelectingCustomerWriteAdapter(
        SqlAccountingWriteSettings(provider=provider, block_rest_http=block_rest),
        rest,
        sdk,
    )
    return selecting, client, sess


def _patch_local_sync(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.services.sync_local_customer_fields",
        lambda *_a, **_k: {"CODE": "patched"},
    )
    monkeypatch.setattr(
        "api.services.read_local_customer_fields",
        lambda *_a, **_k: {"CODE": "patched"},
    )


def test_rest_provider_posts_sigv4_path(monkeypatch):
    _patch_local_sync(monkeypatch)
    selecting, client, sess = _selecting(provider=PROVIDER_REST)
    svc = CustomerService(
        api_settings=_api_settings(),
        write_adapter=selecting,
    )
    req = CustomerRequest(code="300-T0001", company_name="Test Co Sdn Bhd", credit_term="30 Days")
    result = svc.create_customer(req)
    assert result.saved is True
    assert result.write_provider == PROVIDER_REST
    assert result.dry_run is False
    assert len(client.posts) == 1
    assert client.posts[0][0].endswith("/customer")
    assert sess.calls == 0


def test_sdk_provider_uses_session_not_rest(monkeypatch):
    _patch_local_sync(monkeypatch)
    selecting, client, sess = _selecting(provider=PROVIDER_SDK)
    svc = CustomerService(api_settings=_api_settings(), write_adapter=selecting)
    result = svc.create_customer(_request())
    assert result.write_provider == PROVIDER_SDK
    assert result.code == "300-T0001"
    assert sess.calls == 1
    assert client.posts == []


def test_sdk_failure_does_not_fallback_to_rest(monkeypatch):
    _patch_local_sync(monkeypatch)
    selecting, client, sess = _selecting(provider=PROVIDER_SDK, session=_CountingSession(fail=True))
    svc = CustomerService(api_settings=_api_settings(), write_adapter=selecting)
    with pytest.raises(SqlAccountingApiError, match="SDK boom"):
        svc.create_customer(_request())
    assert client.posts == []
    assert sess.calls == 1


def test_sdk_duplicate_customer_raises_422_without_rest(monkeypatch):
    _patch_local_sync(monkeypatch)
    selecting, client, _sess = _selecting(
        provider=PROVIDER_SDK,
        session=_CountingSession(duplicate=True),
    )
    svc = CustomerService(api_settings=_api_settings(), write_adapter=selecting)
    with pytest.raises(SqlAccountingApiError, match="already exists") as excinfo:
        svc.create_customer(_request())
    assert excinfo.value.status_code == 422
    assert client.posts == []


def test_concurrent_sdk_creates_are_serialized(monkeypatch):
    _patch_local_sync(monkeypatch)
    session = _CountingSession(hold_seconds=0.05)
    selecting, client, _ = _selecting(provider=PROVIDER_SDK, session=session)
    svc = CustomerService(api_settings=_api_settings(), write_adapter=selecting)
    errors: list[BaseException] = []
    results: list[str] = []

    def _worker(idx: int) -> None:
        try:
            out = svc.create_customer(
                CustomerRequest(
                    code=f"300-T{idx:04d}",
                    company_name="Test Co Sdn Bhd",
                    credit_term="30 Days",
                )
            )
            results.append(out.code)
        except BaseException as exc:  # noqa: BLE001 — collect for assertion
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert errors == []
    assert len(results) == 4
    assert session.calls == 4
    assert session.max_active == 1
    assert client.posts == []


def test_dry_run_skips_rest_and_sdk(monkeypatch):
    selecting, client, sess = _selecting(provider=PROVIDER_REST)
    svc = CustomerService(api_settings=_api_settings(dry_run=True), write_adapter=selecting)
    result = svc.create_customer(_request())
    assert result.dry_run is True
    assert result.write_provider == PROVIDER_REST
    assert result.request_preview is not None
    assert result.request_preview["method"] == "POST"
    assert client.posts == []
    assert sess.calls == 0

    selecting_sdk, client2, sess2 = _selecting(provider=PROVIDER_SDK)
    monkeypatch.setenv("SQL_ACCOUNTING_WRITE_PROVIDER", "Sdk")
    svc2 = CustomerService(api_settings=_api_settings(dry_run=True), write_adapter=selecting_sdk)
    result2 = svc2.create_customer(_request())
    assert result2.dry_run is True
    assert result2.write_provider == PROVIDER_SDK
    assert result2.request_preview["method"] == "COM"
    assert client2.posts == []
    assert sess2.calls == 0


def test_rollback_to_rest_after_sdk(monkeypatch):
    """Provider=Rest restores REST path without code changes (rollback)."""
    _patch_local_sync(monkeypatch)
    sdk_sel, _client_sdk, sess = _selecting(provider=PROVIDER_SDK)
    svc_sdk = CustomerService(api_settings=_api_settings(), write_adapter=sdk_sel)
    assert svc_sdk.create_customer(_request()).write_provider == PROVIDER_SDK
    assert sess.calls == 1

    rest_sel, client_rest, sess2 = _selecting(provider=PROVIDER_REST, rest_client=_FakeRestClient())
    svc_rest = CustomerService(api_settings=_api_settings(), write_adapter=rest_sel)
    out = svc_rest.create_customer(
        CustomerRequest(code="300-T0002", company_name="Rollback Co", credit_term="30 Days")
    )
    assert out.write_provider == PROVIDER_REST
    assert len(client_rest.posts) == 1
    assert sess2.calls == 0


def test_block_rest_http_refuses_rest_provider():
    selecting, client, _ = _selecting(provider=PROVIDER_REST, block_rest=True)
    svc = CustomerService(api_settings=_api_settings(), write_adapter=selecting)
    with pytest.raises(CustomerConfigurationError, match="BLOCK_REST_HTTP"):
        svc.create_customer(_request())
    assert client.posts == []


def test_sdk_refuses_when_live_com_disabled():
    selecting, client, sess = _selecting(provider=PROVIDER_SDK, sdk_allow=False)
    svc = CustomerService(api_settings=_api_settings(), write_adapter=selecting)
    with pytest.raises(CustomerConfigurationError, match="ALLOW_LIVE_COM"):
        svc.create_customer(_request())
    assert client.posts == []
    assert sess.calls == 0


def test_normalize_write_provider_defaults_to_rest():
    from api.config.sql_accounting_write import normalize_write_provider

    assert normalize_write_provider(None) == PROVIDER_REST
    assert normalize_write_provider("") == PROVIDER_REST
    assert normalize_write_provider("rest") == PROVIDER_REST
    assert normalize_write_provider("Sdk") == PROVIDER_SDK
    assert normalize_write_provider("SDK") == PROVIDER_SDK


def test_create_customer_via_com_duplicate(monkeypatch):
    from api.adapters import sqlacc_customer_writer as writer

    class _Biz:
        def FindKeyByRef(self, field, value):
            return 42

    class _Objects:
        def Find(self, name):
            return _Biz()

    class _App:
        BizObjects = _Objects()

    with pytest.raises(SqlAccountingApiError, match="already exists"):
        writer.create_customer_via_com(_App(), _request(), control_account_override="300-000")


def test_create_customer_via_com_rejects_oversized_code(monkeypatch):
    from api.adapters import sqlacc_customer_writer as writer

    class _Field:
        Size = 10

        def __init__(self, name: str):
            self.FieldName = name
            self.AsString = ""

    class _Fields:
        def FindField(self, name):
            return _Field(name)

    class _Dataset:
        Fields = _Fields()

    class _DataSets:
        def Find(self, name):
            return _Dataset()

    class _Biz:
        DataSets = _DataSets()

        def FindKeyByRef(self, field, value):
            return None

        def New(self):
            return None

    class _Objects:
        def Find(self, name):
            return _Biz()

    class _App:
        BizObjects = _Objects()

    monkeypatch.setattr(writer, "resolve_control_account", lambda *_a, **_k: "300-000")
    req = CustomerRequest(
        code="300-EQ125914",
        company_name="Too Long Code Co",
        credit_term="30 Days",
    )
    with pytest.raises(SqlAccountingApiError, match="exceeds AR_CUSTOMER.CODE size"):
        writer.create_customer_via_com(_App(), req, control_account_override="300-000")


def test_guest_duplicate_detector_accepts_sdk_message():
    from main import _is_duplicate_customer_code_error

    assert _is_duplicate_customer_code_error(
        "Customer code '300-A0001' already exists (duplicate CODE)."
    )
    assert _is_duplicate_customer_code_error(
        'GL_ACC_CODE Problematic key value is "CODE"'
    )
