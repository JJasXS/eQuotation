"""Health check endpoints."""
from fastapi import APIRouter
from api.models import APIResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=APIResponse)
async def health_check():
    """
    Health check endpoint.
    
    Returns:
        Health status and API version
    """
    return APIResponse(
        success=True,
        message="API is healthy",
        data={
            "status": "healthy",
            "version": "1.0.0"
        }
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
