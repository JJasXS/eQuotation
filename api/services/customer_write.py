"""REST / SDK write adapters for customer create (sqlSign SelectingWriteAdapter pattern)."""
from __future__ import annotations

import logging
from typing import Any, Protocol

from api.adapters.sqlacc_customer_writer import create_customer_via_com
from api.adapters.sqlacc_session import SqlAccSessionError, SqlAccSessionManager, get_sqlacc_session_manager
from api.clients import SqlAccountingApiClient, SqlAccountingApiError
from api.config.sql_acc_sdk import SqlAccSdkSettings, load_sql_acc_sdk_settings, redact_sdk_settings_for_log
from api.config.sql_accounting_api import SqlAccountingApiSettings, redact_settings_for_log
from api.config.sql_accounting_write import (
    PROVIDER_REST,
    PROVIDER_SDK,
    SqlAccountingWriteSettings,
    load_sql_accounting_write_settings,
)
from api.models import CustomerRequest, CustomerResponse

logger = logging.getLogger(__name__)


class CustomerConfigurationError(Exception):
    """Raised when REST/SDK environment is incomplete or REST is blocked."""


class CustomerWriteAdapter(Protocol):
    def create_customer(
        self,
        customer_request: CustomerRequest,
        payload: dict[str, Any],
    ) -> CustomerResponse: ...


class RestCustomerWriteAdapter:
    """SigV4 POST to SQL Accounting customer create path (current production path)."""

    def __init__(
        self,
        api_settings: SqlAccountingApiSettings,
        api_client: SqlAccountingApiClient | None = None,
    ) -> None:
        self._api_settings = api_settings
        self._api_client = api_client or SqlAccountingApiClient(api_settings)

    def create_customer(
        self,
        customer_request: CustomerRequest,
        payload: dict[str, Any],
    ) -> CustomerResponse:
        settings = self._api_settings
        url = settings.resolved_create_url()

        if not settings.access_key or not settings.secret_key:
            raise CustomerConfigurationError(
                "SQL_API_ACCESS_KEY and SQL_API_SECRET_KEY must be set for live customer creation."
            )
        if not settings.customer_create_path.strip():
            raise CustomerConfigurationError(
                "SQL_API_CUSTOMER_CREATE_PATH must be set to the documented API path "
                "(TODO: configure in .env)."
            )

        logger.info(
            "Creating customer via SQL Accounting REST API: code=%s url=%s",
            customer_request.code,
            url,
        )

        try:
            status, parsed, raw = self._api_client.post_json(url, payload)
        except SqlAccountingApiError:
            raise

        if status >= 400:
            detail = raw
            if parsed is not None:
                detail = str(parsed.get("message") or parsed.get("error") or parsed)
            raise SqlAccountingApiError(
                f"SQL Accounting API returned HTTP {status}: {detail}",
                status_code=status,
                response_body=raw,
            )

        if parsed is None:
            raw_preview = (raw or "").strip().replace("\n", " ")[:240]
            raise SqlAccountingApiError(
                "SQL Accounting API returned non-JSON success response; insert cannot be confirmed. "
                f"Preview: {raw_preview or '(empty body)'}",
                status_code=502,
                response_body=raw,
            )
        return _customer_response_from_api(
            parsed,
            customer_request,
            raw,
            write_provider=PROVIDER_REST,
        )


class SdkCustomerWriteAdapter:
    """COM SDK create via STA session. Never falls through to REST."""

    def __init__(
        self,
        sdk_settings: SqlAccSdkSettings | None = None,
        session_manager: SqlAccSessionManager | None = None,
        *,
        writer: Any | None = None,
    ) -> None:
        self._sdk_settings = sdk_settings if sdk_settings is not None else load_sql_acc_sdk_settings()
        self._session_manager = session_manager
        self._writer = writer or create_customer_via_com

    def create_customer(
        self,
        customer_request: CustomerRequest,
        payload: dict[str, Any],
    ) -> CustomerResponse:
        settings = self._sdk_settings
        if not settings.allow_live_com:
            raise CustomerConfigurationError(
                "Provider=Sdk but SQLACC_SDK_ALLOW_LIVE_COM is false; refusing COM create."
            )
        missing = settings.missing_login_fields()
        if missing:
            raise CustomerConfigurationError(
                "Provider=Sdk Login incomplete: " + ", ".join(missing)
            )

        manager = self._session_manager or get_sqlacc_session_manager()
        logger.info(
            "Creating customer via SQLAcc SDK: code=%s settings=%s",
            customer_request.code,
            redact_sdk_settings_for_log(settings),
        )

        override = settings.customer_control_account or None

        def _action(app: Any) -> dict[str, Any]:
            return self._writer(
                app,
                customer_request,
                control_account_override=override,
            )

        try:
            upstream = manager.run(_action)
        except SqlAccountingApiError:
            raise
        except SqlAccSessionError as exc:
            raise SqlAccountingApiError(str(exc), status_code=503) from exc
        except Exception as exc:
            logger.exception("SDK customer create failed")
            raise SqlAccountingApiError(
                f"SDK customer create failed: {exc}",
                status_code=502,
            ) from exc

        code = str(
            (upstream or {}).get("code")
            or customer_request.code
            or ""
        )
        return CustomerResponse(
            code=code,
            company_name=str(customer_request.company_name),
            credit_term=customer_request.credit_term,
            saved=True,
            dry_run=False,
            request_preview=None,
            raw_response_snippet=None,
            upstream_response=upstream if isinstance(upstream, dict) else {"result": upstream},
            write_provider=PROVIDER_SDK,
        )


class SelectingCustomerWriteAdapter:
    """
    Route customer creates to REST or SDK from write settings.

    Critical: SDK success/failure never auto-retries via REST (no double write).
    """

    def __init__(
        self,
        write_settings: SqlAccountingWriteSettings,
        rest_adapter: CustomerWriteAdapter,
        sdk_adapter: CustomerWriteAdapter,
    ) -> None:
        self._write_settings = write_settings
        self._rest = rest_adapter
        self._sdk = sdk_adapter

    @property
    def provider(self) -> str:
        return self._write_settings.provider

    def create_customer(
        self,
        customer_request: CustomerRequest,
        payload: dict[str, Any],
    ) -> CustomerResponse:
        if self._write_settings.is_sdk:
            return self._sdk.create_customer(customer_request, payload)

        if self._write_settings.block_rest_http:
            raise CustomerConfigurationError(
                "SQL_ACCOUNTING_BLOCK_REST_HTTP is true; REST customer create is refused. "
                "Set SQL_ACCOUNTING_WRITE_PROVIDER=Sdk or disable the block."
            )
        return self._rest.create_customer(customer_request, payload)


def _customer_response_from_api(
    parsed: dict[str, Any] | None,
    request: CustomerRequest,
    raw: str,
    *,
    write_provider: str,
) -> CustomerResponse:
    code = request.code
    company_name = request.company_name
    if parsed:
        code = (
            parsed.get("code")
            or parsed.get("customerCode")
            or (parsed.get("data") or {}).get("code")
            or (parsed.get("customer") or {}).get("code")
            or code
        )
        company_name = (
            parsed.get("company_name")
            or parsed.get("companyName")
            or parsed.get("companyname")
            or (parsed.get("customer") or {}).get("company_name")
            or (parsed.get("customer") or {}).get("companyname")
            or company_name
        )
    return CustomerResponse(
        code=str(code),
        company_name=str(company_name),
        credit_term=request.credit_term,
        saved=True,
        dry_run=False,
        request_preview=None,
        raw_response_snippet=raw[:2000] if raw else None,
        upstream_response=parsed,
        write_provider=write_provider,
    )


def build_customer_write_adapter(
    api_settings: SqlAccountingApiSettings,
    *,
    write_settings: SqlAccountingWriteSettings | None = None,
    api_client: SqlAccountingApiClient | None = None,
    sdk_settings: SqlAccSdkSettings | None = None,
    session_manager: SqlAccSessionManager | None = None,
) -> SelectingCustomerWriteAdapter:
    """Factory used by CustomerService (injectable for tests)."""
    write = write_settings or load_sql_accounting_write_settings()
    rest = RestCustomerWriteAdapter(api_settings, api_client=api_client)
    sdk = SdkCustomerWriteAdapter(sdk_settings=sdk_settings, session_manager=session_manager)
    logger.info(
        "Customer write provider=%s block_rest_http=%s api=%s",
        write.provider,
        write.block_rest_http,
        redact_settings_for_log(api_settings),
    )
    return SelectingCustomerWriteAdapter(write, rest, sdk)
