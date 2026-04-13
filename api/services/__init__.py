"""Services for SQL Account integration (REST API + COM read helpers)."""
from __future__ import annotations

import logging
from typing import Any

from api.adapters import COMConnectionError, COMConnectionHandler
from api.clients import SqlAccountingApiClient, SqlAccountingApiError
from api.config import load_sql_accounting_api_settings
from api.config.sql_accounting_api import redact_settings_for_log
from api.models import CustomerRequest, CustomerResponse
from api.services.customer_payload import build_customer_create_payload
from api.services.local_customer_sync import LocalCustomerSyncRequest, read_local_customer_fields, sync_local_customer_fields

logger = logging.getLogger(__name__)


class COMOperationError(Exception):
    """Raised when SQL Account COM operations fail."""


class CustomerConfigurationError(Exception):
    """Raised when SQL Accounting API environment is incomplete for a live create."""


class CustomerService:
    """Customer operations: create via SQL Accounting API (SigV4); read metadata via COM."""

    def __init__(
        self,
        com_handler: COMConnectionHandler | None = None,
        api_settings: Any | None = None,
        api_client: SqlAccountingApiClient | None = None,
    ) -> None:
        self.com_handler = com_handler or COMConnectionHandler()
        self._api_settings = api_settings if api_settings is not None else load_sql_accounting_api_settings()
        self._api_client = api_client or SqlAccountingApiClient(self._api_settings)

    def create_customer(self, customer_request: CustomerRequest) -> CustomerResponse:
        """Create customer in SQL Accounting via signed REST API (no COM / no direct SQL)."""
        settings = self._api_settings
        payload = build_customer_create_payload(customer_request)
        url = settings.resolved_create_url()

        if settings.dry_run:
            logger.info(
                "SQL_API_DRY_RUN enabled: skipping HTTP POST. Target URL would be %s. Settings=%s",
                url,
                redact_settings_for_log(settings),
            )
            return CustomerResponse(
                code=customer_request.code or "",
                company_name=customer_request.company_name,
                credit_term=customer_request.credit_term,
                saved=True,
                dry_run=True,
                request_preview={
                    "method": "POST",
                    "url": url,
                    "body": payload,
                },
                upstream_response=None,
            )

        if not settings.access_key or not settings.secret_key:
            raise CustomerConfigurationError(
                "SQL_API_ACCESS_KEY and SQL_API_SECRET_KEY must be set for live customer creation."
            )
        if not settings.customer_create_path.strip():
            raise CustomerConfigurationError(
                "SQL_API_CUSTOMER_CREATE_PATH must be set to the documented API path (TODO: configure in .env)."
            )

        logger.info(
            "Creating customer via SQL Accounting API: code=%s url=%s",
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
        response = self._customer_response_from_api(parsed, customer_request, raw)

        sync_request = LocalCustomerSyncRequest(
            code=response.code,
            area=customer_request.area,
            currency_code=customer_request.currency_code,
            tin=customer_request.tin,
            brn=customer_request.brn,
            brn2=customer_request.brn2,
            sales_tax_no=customer_request.sales_tax_no,
            service_tax_no=customer_request.service_tax_no,
            tax_exp_date=customer_request.tax_exp_date,
            tax_exempt_no=customer_request.tax_exempt_no,
            idtype=customer_request.idtype,
            attention=customer_request.attention,
            address1=customer_request.address1,
            address2=customer_request.address2,
            address3=customer_request.address3,
            address4=customer_request.address4,
            postcode=customer_request.postcode,
            city=customer_request.city,
            state=customer_request.state,
            country=customer_request.country,
            phone1=customer_request.phone,
            email=customer_request.email or customer_request.udf_email,
        )

        if any(value not in (None, "") for key, value in sync_request.model_dump().items() if key != "code"):
            try:
                response.local_db_snapshot = sync_local_customer_fields(sync_request)
            except Exception:
                logger.exception("Post-create local customer sync failed for code=%s", response.code)
                try:
                    response.local_db_snapshot = read_local_customer_fields(response.code)
                except Exception:
                    logger.exception("Post-create local readback failed for code=%s", response.code)

        return response

    @staticmethod
    def _customer_response_from_api(
        parsed: dict[str, Any] | None,
        request: CustomerRequest,
        raw: str,
    ) -> CustomerResponse:
        """
        TODO(sql-accounting-api): Map the real success JSON to ``CustomerResponse`` using API docs.
        """
        code = request.code
        company_name = request.company_name
        if parsed:
            # TODO: Confirm response keys (e.g. data.code, customer.code, CustomerCode).
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
        )

    def get_customer_state(self, customer_code: str) -> dict[str, Any]:
        """Read customer status/submission state from SQL Account via COM."""
        try:
            with self.com_handler.session() as biz:
                customer_obj = biz.BizObjects.Find("AR_CUSTOMER")
                params = customer_obj.Params
                if params.Count < 1:
                    raise COMOperationError("AR_CUSTOMER params are not available.")

                params.Items(0).AsString = customer_code
                customer_obj.Open()

                main_dataset = customer_obj.DataSets.Find("MainDataSet")
                status = self._get_field_as_string(main_dataset, "STATUS")
                submission_type = self._get_field_as_string(main_dataset, "SUBMISSIONTYPE")

                normalized_submission = submission_type.strip() if submission_type is not None else ""
                # In this environment, editable records are Active and typically use SUBMISSIONTYPE 0/empty.
                is_editable = status == "A" and normalized_submission in ("", "0", "NULL")

                return {
                    "code": customer_code,
                    "status": status,
                    "submission_type": None if normalized_submission in ("", "NULL") else normalized_submission,
                    "is_editable": is_editable,
                    "rule": "Expected STATUS='A' and SUBMISSIONTYPE in {0, NULL, empty}.",
                    "source": "com",
                }
        except COMConnectionError:
            raise
        except COMOperationError:
            raise
        except Exception as exc:
            logger.exception("Failed to inspect customer state for code '%s'", customer_code)
            raise COMOperationError(str(exc)) from exc

    def health_check(self) -> dict[str, Any]:
        """Report API configuration and optional COM availability for read helpers."""
        settings = self._api_settings
        api_ready = bool(
            settings.access_key
            and settings.secret_key
            and settings.customer_create_path.strip()
        )
        result: dict[str, Any] = {
            "status": "healthy",
            "customer_create": {
                "backend": "sql_accounting_api",
                "dry_run": settings.dry_run,
                "api_configured": api_ready or settings.dry_run,
                "host": settings.host,
                "region": settings.region,
            },
            "com_state_reader": {"available": False},
        }
        try:
            with self.com_handler.session() as biz:
                prog_id = getattr(self.com_handler, "prog_id", "SQLAcc.BizApp")
                result["com_state_reader"] = {"available": biz is not None, "prog_id": prog_id}
        except COMConnectionError as exc:
            logger.warning("COM unavailable for state reader: %s", exc)
            result["com_state_reader"] = {"available": False, "error": str(exc)}
        return result

    def get_customer_metadata(self) -> dict[str, Any]:
        """Return customer COM datasets and field defaults for debugging."""
        try:
            with self.com_handler.session() as biz:
                customer_obj = biz.BizObjects.Find("AR_CUSTOMER")
                customer_obj.New()
                datasets = customer_obj.DataSets

                dataset_items: list[dict[str, Any]] = []
                for i in range(datasets.Count):
                    dataset = datasets.Items(i)
                    fields = dataset.Fields
                    field_items: list[dict[str, Any]] = []
                    for j in range(fields.Count):
                        field = fields.Items(j)
                        field_items.append(
                            {
                                "name": field.FieldName,
                                "value": field.AsString,
                                "data_type": field.DataType,
                                "size": field.DataSize,
                            }
                        )
                    dataset_items.append({"name": dataset.Name, "fields": field_items})

                return {"biz_object": "AR_CUSTOMER", "datasets": dataset_items}
        except COMConnectionError:
            raise
        except Exception as exc:
            logger.exception("Failed to inspect AR_CUSTOMER metadata")
            raise COMOperationError(str(exc)) from exc

    @staticmethod
    def _get_field_as_string(dataset: object, field_name: str) -> str:
        """Safely get a field value from COM dataset as string."""
        field = dataset.Fields.FindField(field_name)
        if field is None:
            return ""
        value = field.AsString
        return "" if value is None else str(value)
