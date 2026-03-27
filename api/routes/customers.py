"""Customer management endpoints via SQL Account COM."""
import logging

from fastapi import APIRouter, HTTPException

from api.adapters import COMConnectionError
from api.models import APIResponse, CustomerRequest
from api.services import CustomerService
from api.services import COMOperationError

router = APIRouter(prefix="/customers", tags=["Customers"])
logger = logging.getLogger(__name__)

# Initialize service
customer_service = CustomerService()


@router.post("", response_model=APIResponse, status_code=201)
async def create_customer(customer_data: CustomerRequest):
    """Create customer using SQLAcc.BizApp COM object."""
    try:
        customer = customer_service.create_customer(customer_data)
        return APIResponse(
            success=True,
            message="Customer created successfully",
            data=customer.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )
    except COMConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"COM connection failed: {str(exc)}"
        )
    except COMOperationError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Customer creation rejected by SQL Account: {str(exc)}"
        )
    except Exception as exc:
        logger.exception("Unhandled error while creating customer")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create customer: {str(exc)}"
        )
