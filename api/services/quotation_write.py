"""REST / SDK write adapters for Sales Quotation (sqlSign SelectingWriteAdapter pattern)."""
from __future__ import annotations

import logging
from typing import Any, Callable, Protocol

from api.adapters.sqlacc_quotation_writer import (
    create_quotation_via_com,
    update_quotation_via_com,
)
from api.adapters.sqlacc_session import SqlAccSessionError, SqlAccSessionManager, get_sqlacc_session_manager
from api.clients import SqlAccountingApiError
from api.config.sql_acc_sdk import SqlAccSdkSettings, load_sql_acc_sdk_settings, redact_sdk_settings_for_log
from api.config.sql_accounting_quotation_write import (
    PROVIDER_REST,
    PROVIDER_SDK,
    SqlAccountingQuotationWriteSettings,
    load_sql_accounting_quotation_write_settings,
)

logger = logging.getLogger(__name__)


class QuotationConfigurationError(Exception):
    """Raised when REST/SDK environment is incomplete or REST is blocked."""


class QuotationWriteAdapter(Protocol):
    def write_quotation(
        self,
        payload: dict[str, Any],
        *,
        is_update: bool,
        dockey: int,
    ) -> dict[str, Any]: ...


class RestQuotationWriteAdapter:
    """Delegates to a caller-provided REST attempt callable (preserves timeout/retry ownership)."""

    def __init__(self, rest_attempt: Callable[[], dict[str, Any]]) -> None:
        self._rest_attempt = rest_attempt

    def write_quotation(
        self,
        payload: dict[str, Any],
        *,
        is_update: bool,
        dockey: int,
    ) -> dict[str, Any]:
        del payload, is_update, dockey
        result = self._rest_attempt()
        if isinstance(result, dict) and "write_provider" not in result:
            result = {**result, "write_provider": PROVIDER_REST}
        return result


class SdkQuotationWriteAdapter:
    """COM SDK create/update via STA session. Never falls through to REST."""

    def __init__(
        self,
        sdk_settings: SqlAccSdkSettings | None = None,
        session_manager: SqlAccSessionManager | None = None,
        *,
        cud_enabled: bool = False,
        create_writer: Any | None = None,
        update_writer: Any | None = None,
    ) -> None:
        self._sdk_settings = sdk_settings if sdk_settings is not None else load_sql_acc_sdk_settings()
        self._session_manager = session_manager
        self._cud_enabled = cud_enabled
        self._create_writer = create_writer or create_quotation_via_com
        self._update_writer = update_writer or update_quotation_via_com

    def write_quotation(
        self,
        payload: dict[str, Any],
        *,
        is_update: bool,
        dockey: int,
    ) -> dict[str, Any]:
        settings = self._sdk_settings
        if not settings.allow_live_com:
            raise QuotationConfigurationError(
                "Provider=Sdk but SQLACC_SDK_ALLOW_LIVE_COM is false; refusing COM quotation write."
            )
        missing = settings.missing_login_fields()
        if missing:
            raise QuotationConfigurationError(
                "Provider=Sdk Login incomplete: " + ", ".join(missing)
            )
        if not self._cud_enabled:
            raise QuotationConfigurationError(
                "Provider=Sdk but SQLACC_SDK_QUOTATION_CUD_ENABLED is false; "
                "refusing SL_QT New/Edit/Save until CUD lab enablement."
            )

        manager = self._session_manager or get_sqlacc_session_manager()
        logger.info(
            "Writing quotation via SQLAcc SDK: docno=%s update=%s settings=%s",
            payload.get("docno"),
            is_update,
            redact_sdk_settings_for_log(settings),
        )

        def _action(app: Any) -> dict[str, Any]:
            if is_update:
                return self._update_writer(app, payload, dockey=dockey)
            return self._create_writer(app, payload)

        try:
            upstream = manager.run(_action)
        except SqlAccountingApiError:
            raise
        except SqlAccSessionError as exc:
            raise SqlAccountingApiError(str(exc), status_code=503) from exc
        except Exception as exc:
            logger.exception("SDK quotation write failed")
            raise SqlAccountingApiError(
                f"SDK quotation write failed: {exc}",
                status_code=502,
            ) from exc

        if not isinstance(upstream, dict):
            upstream = {"result": upstream}
        return {
            "success": True,
            "dockey": upstream.get("dockey") or 0,
            "docno": upstream.get("docno") or payload.get("docno"),
            "message": upstream.get("message") or "Quotation saved successfully",
            "upstream": upstream,
            "write_provider": PROVIDER_SDK,
        }


class SelectingQuotationWriteAdapter:
    """
    Route quotation writes to REST or SDK from quotation write settings.

    Critical: SDK success/failure never auto-retries via REST (no double write).
    """

    def __init__(
        self,
        write_settings: SqlAccountingQuotationWriteSettings,
        rest_adapter: QuotationWriteAdapter,
        sdk_adapter: QuotationWriteAdapter,
    ) -> None:
        self._write_settings = write_settings
        self._rest = rest_adapter
        self._sdk = sdk_adapter

    @property
    def provider(self) -> str:
        return self._write_settings.provider

    @property
    def is_sdk(self) -> bool:
        return self._write_settings.is_sdk

    def write_quotation(
        self,
        payload: dict[str, Any],
        *,
        is_update: bool,
        dockey: int,
    ) -> dict[str, Any]:
        if self._write_settings.is_sdk:
            return self._sdk.write_quotation(payload, is_update=is_update, dockey=dockey)

        if self._write_settings.block_rest_http:
            raise QuotationConfigurationError(
                "SQL_ACCOUNTING_BLOCK_REST_HTTP is true; REST quotation write is refused. "
                "Set SQL_ACCOUNTING_QUOTATION_WRITE_PROVIDER=Sdk or disable the block."
            )
        return self._rest.write_quotation(payload, is_update=is_update, dockey=dockey)


def build_quotation_write_adapter(
    *,
    write_settings: SqlAccountingQuotationWriteSettings | None = None,
    rest_attempt: Callable[[], dict[str, Any]] | None = None,
    sdk_settings: SqlAccSdkSettings | None = None,
    session_manager: SqlAccSessionManager | None = None,
    create_writer: Any | None = None,
    update_writer: Any | None = None,
) -> SelectingQuotationWriteAdapter:
    """Factory for quotation create/update (injectable for tests)."""
    write = write_settings or load_sql_accounting_quotation_write_settings()
    if rest_attempt is None:
        raise QuotationConfigurationError("rest_attempt callable is required for Rest path")
    rest = RestQuotationWriteAdapter(rest_attempt)
    sdk = SdkQuotationWriteAdapter(
        sdk_settings=sdk_settings,
        session_manager=session_manager,
        cud_enabled=write.cud_enabled,
        create_writer=create_writer,
        update_writer=update_writer,
    )
    logger.info(
        "Quotation write provider=%s block_rest_http=%s cud_enabled=%s",
        write.provider,
        write.block_rest_http,
        write.cud_enabled,
    )
    return SelectingQuotationWriteAdapter(write, rest, sdk)
