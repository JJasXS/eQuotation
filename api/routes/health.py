"""Health check endpoints."""
from fastapi import APIRouter
from api.models import APIResponse
from api.services import CustomerService

router = APIRouter(tags=["Health"])
customer_service = CustomerService()


@router.get("/health", response_model=APIResponse)
async def health_check():
    """
    Health check endpoint.
    
    Returns:
        Health status and API version
    """
    result = customer_service.health_check()
    is_healthy = result.get("status") == "healthy"
    return APIResponse(
        success=is_healthy,
        message="API and COM are healthy" if is_healthy else "API running but COM unavailable",
        data=result,
        errors=None if is_healthy else [result.get("error", "Unknown COM error")]
    )


@router.get("/", response_model=APIResponse)
async def root():
    """Root endpoint - API info."""
    return APIResponse(
        success=True,
        message="eQuotation API",
        data={
            "name": "eQuotation REST API",
            "version": "1.0.0",
            "description": "REST API layer for SQL Account integration"
        }
    )
