"""Debug endpoints for COM metadata inspection."""
import logging

from fastapi import APIRouter, HTTPException

from api.adapters import COMConnectionError
from api.models import APIResponse
from api.services import COMOperationError, CustomerService

router = APIRouter(prefix="/debug/com", tags=["Debug"])
logger = logging.getLogger(__name__)
customer_service = CustomerService()


@router.get("/customer-metadata", response_model=APIResponse)
async def customer_metadata():
    """Read-only AR_CUSTOMER metadata from SQLAcc COM object."""
    try:
        metadata = customer_service.get_customer_metadata()
        return APIResponse(
            success=True,
            message="Customer metadata retrieved successfully",
            data=metadata,
        )
    except COMConnectionError as exc:
        raise HTTPException(status_code=503, detail=f"COM connection failed: {str(exc)}")
    except COMOperationError as exc:
        raise HTTPException(
            status_code=422, detail=f"COM metadata inspection failed: {str(exc)}"
        )
    except Exception as exc:
        logger.exception("Unhandled error while reading customer metadata")
        raise HTTPException(status_code=500, detail=f"Failed to read metadata: {str(exc)}")
