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
                customer = biz.Customer()
                customer.New()

                customer.Code = customer_request.code
                customer.CompanyName = customer_request.company_name
                customer.CreditTerm = customer_request.credit_term

                if customer_request.phone:
                    self._set_if_exists(customer, "Phone1", customer_request.phone)
                if customer_request.address1:
                    self._set_if_exists(customer, "Address1", customer_request.address1)

                self._try_create_branch(biz, customer_request)

                save_result = customer.Save()
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

    @staticmethod
    def _set_if_exists(obj: object, attr_name: str, value: Any) -> None:
        """Set COM field only when object exposes the field."""
        if hasattr(obj, attr_name):
            setattr(obj, attr_name, value)

    def _try_create_branch(self, biz: object, customer_request: CustomerRequest) -> None:
        """
        Attempt to create a customer branch when API exposes it.

        SQL Account COM APIs vary by version; branch creation is best-effort.
        """
        if not customer_request.address1 and not customer_request.phone:
            return

        try:
            branch_obj = None
            if hasattr(biz, "CustomerBranch"):
                branch_obj = biz.CustomerBranch()
                branch_obj.New()
            elif hasattr(biz, "CustomerBranches"):
                branches = biz.CustomerBranches()
                if hasattr(branches, "New"):
                    branch_obj = branches.New()

            if branch_obj is None:
                return

            self._set_if_exists(branch_obj, "Code", customer_request.code)
            self._set_if_exists(branch_obj, "BranchType", "B")
            self._set_if_exists(branch_obj, "BranchName", "BILLING")
            if customer_request.address1:
                self._set_if_exists(branch_obj, "Address1", customer_request.address1)
            if customer_request.phone:
                self._set_if_exists(branch_obj, "Phone1", customer_request.phone)

            if hasattr(branch_obj, "Save"):
                branch_obj.Save()
        except Exception:
            # Do not fail customer creation if branch API differs by SQL Account build.
            logger.exception("Branch creation skipped due to COM API mismatch")
