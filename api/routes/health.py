"""Health check endpoints."""
from fastapi import APIRouter

from api.models import APIResponse
from api.services import CustomerService

router = APIRouter(tags=["Health"])
customer_service = CustomerService()


@router.get("/health", response_model=APIResponse)
async def health_check():
    """
    Health check: process is up; ``data.customer_create`` shows SigV4 API readiness.

    COM availability is listed under ``com_state_reader`` for optional post-create reads.
    """
    result = customer_service.health_check()
    cc = result.get("customer_create", {})
    warnings: list[str] = []
    if not cc.get("dry_run") and not cc.get("api_configured"):
        warnings.append(
            "SQL Accounting API not configured for live create (set keys, path, or SQL_API_DRY_RUN=true)"
        )
    return APIResponse(
        success=True,
        message="eQuotation API is running",
        data=result,
        errors=warnings or None,
    )
