"""Services for SQL Account COM middleware."""
from __future__ import annotations

import logging
from typing import Any

from api.adapters import COMConnectionError, COMConnectionHandler
from api.models import CustomerRequest, CustomerResponse

logger = logging.getLogger(__name__)


class COMOperationError(Exception):
    """Raised when SQL Account COM operations fail."""


class CustomerService:
    """Service layer for customer operations through COM only."""

    def __init__(self, com_handler: COMConnectionHandler | None = None) -> None:
        self.com_handler = com_handler or COMConnectionHandler()

    def create_customer(self, customer_request: CustomerRequest) -> CustomerResponse:
        """Create customer in SQL Account using SQLAcc.BizApp COM."""
        try:
            with self.com_handler.session() as biz:
                customer_obj = biz.BizObjects.Find("AR_CUSTOMER")
                customer_obj.New()

                main_dataset = customer_obj.DataSets.Find("MainDataSet")
                self._set_field(main_dataset, "CODE", customer_request.code, required=True)
                self._set_field(main_dataset, "COMPANYNAME", customer_request.company_name, required=True)
                self._set_field(
                    main_dataset,
                    "CREDITTERM",
                    self._normalize_credit_term(customer_request.credit_term),
                    required=True,
                )
                self._set_field(main_dataset, "CONTROLACCOUNT", customer_request.control_account)
                self._set_field(main_dataset, "COMPANYCATEGORY", customer_request.company_category)
                self._set_field(main_dataset, "AREA", customer_request.area)
                self._set_field(main_dataset, "AGENT", customer_request.agent)
                self._set_field(main_dataset, "STATEMENTTYPE", customer_request.statement_type)
                self._set_field(main_dataset, "CURRENCYCODE", customer_request.currency_code)
                self._set_field(main_dataset, "AGINGON", customer_request.aging_on)
                self._set_field(main_dataset, "STATUS", customer_request.status)
                self._set_field(
                    main_dataset,
                    "SUBMISSIONTYPE",
                    customer_request.submission_type,
                    allow_null=True,
                )
                self._set_field(main_dataset, "BRN", customer_request.brn)
                self._set_field(main_dataset, "BRN2", customer_request.brn2)
                self._set_field(main_dataset, "TIN", customer_request.tin)
                self._set_field(main_dataset, "SALESTAXNO", customer_request.sales_tax_no)
                self._set_field(main_dataset, "SERVICETAXNO", customer_request.service_tax_no)
                self._set_field(main_dataset, "TAXEXEMPTNO", customer_request.tax_exempt_no)
                self._set_field(main_dataset, "TAXEXPDATE", customer_request.tax_exp_date)
                self._set_field(main_dataset, "UDF_Email", customer_request.udf_email)
                self._set_field(main_dataset, "ATTACHMENTS", customer_request.attachments)

                self._set_branch_field(customer_obj, "CODE", customer_request.code)
                self._set_branch_field(customer_obj, "BRANCHTYPE", customer_request.branch_type)
                self._set_branch_field(customer_obj, "BRANCHNAME", customer_request.branch_name)
                self._set_branch_field(customer_obj, "DTLKEY", customer_request.branch_dtlkey)
                self._set_branch_field(customer_obj, "ADDRESS1", customer_request.address1)
                self._set_branch_field(customer_obj, "ADDRESS2", customer_request.address2)
                self._set_branch_field(customer_obj, "ADDRESS3", customer_request.address3)
                self._set_branch_field(customer_obj, "ADDRESS4", customer_request.address4)
                self._set_branch_field(customer_obj, "POSTCODE", customer_request.postcode)
                self._set_branch_field(customer_obj, "CITY", customer_request.city)
                self._set_branch_field(customer_obj, "STATE", customer_request.state)
                self._set_branch_field(customer_obj, "COUNTRY", customer_request.country)
                self._set_branch_field(customer_obj, "ATTENTION", customer_request.attention)
                self._set_branch_field(customer_obj, "PHONE1", customer_request.phone)
                self._set_branch_field(customer_obj, "PHONE2", customer_request.phone2)
                self._set_branch_field(customer_obj, "MOBILE", customer_request.mobile)
                self._set_branch_field(customer_obj, "FAX1", customer_request.fax1)
                self._set_branch_field(customer_obj, "FAX2", customer_request.fax2)
                self._set_branch_field(customer_obj, "EMAIL", customer_request.email or customer_request.udf_email)

                save_result = customer_obj.Save()
                if save_result is False:
                    raise COMOperationError(
                        "Customer Save() returned False. Required fields may be missing or invalid."
                    )

                return CustomerResponse(
                    code=customer_request.code,
                    company_name=customer_request.company_name,
                    credit_term=customer_request.credit_term,
                    phone=customer_request.phone,
                    address1=customer_request.address1,
                    saved=True,
                )
        except COMConnectionError:
            raise
        except COMOperationError:
            raise
        except Exception as exc:
            logger.exception("Unexpected COM error during customer creation")
            raise COMOperationError(str(exc)) from exc

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
                }
        except COMConnectionError:
            raise
        except COMOperationError:
            raise
        except Exception as exc:
            logger.exception("Failed to inspect customer state for code '%s'", customer_code)
            raise COMOperationError(str(exc)) from exc

    def health_check(self) -> dict[str, Any]:
        """Check if COM server can be instantiated."""
        try:
            with self.com_handler.session() as biz:
                prog_id = getattr(self.com_handler, "prog_id", "SQLAcc.BizApp")
                connected = biz is not None
                return {"status": "healthy", "com_connected": connected, "prog_id": prog_id}
        except COMConnectionError as exc:
            logger.exception("COM health check failed")
            return {"status": "unhealthy", "com_connected": False, "error": str(exc)}

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
    def _set_field(
        dataset: object,
        field_name: str,
        value: Any,
        required: bool = False,
        allow_null: bool = False,
    ) -> None:
        """Set a COM dataset field using AsString fallback."""
        if value is None:
            if allow_null:
                field = dataset.Fields.FindField(field_name)
                if field is not None:
                    field.Value = None
                return
            if required:
                raise COMOperationError(
                    f"Field '{field_name}' is required for dataset '{dataset.Name}'."
                )
            return
        if isinstance(value, str) and value.strip() == "":
            if allow_null:
                field = dataset.Fields.FindField(field_name)
                if field is not None:
                    field.Value = None
                return
            if required:
                raise COMOperationError(
                    f"Field '{field_name}' is required for dataset '{dataset.Name}'."
                )
            return
        field = dataset.Fields.FindField(field_name)
        if field is None:
            if required:
                raise COMOperationError(
                    f"Field '{field_name}' not found in dataset '{dataset.Name}'."
                )
            return
        field.AsString = str(value)

    def _set_branch_field(self, customer_obj: object, field_name: str, value: Any) -> None:
        """Set branch-related fields in cdsBranch when available."""
        try:
            branch_dataset = customer_obj.DataSets.Find("cdsBranch")
            self._set_field(branch_dataset, field_name, value, required=False)
        except Exception:
            logger.exception("Unable to set branch field '%s'", field_name)

    @staticmethod
    def _normalize_credit_term(credit_term: str) -> str:
        """Normalize numeric credit term into SQL Account wording."""
        normalized = (credit_term or "").strip()
        if normalized.isdigit():
            return f"{normalized} Days"
        return normalized

    @staticmethod
    def _get_field_as_string(dataset: object, field_name: str) -> str:
        """Safely get a field value from COM dataset as string."""
        field = dataset.Fields.FindField(field_name)
        if field is None:
            return ""
        value = field.AsString
        return "" if value is None else str(value)
