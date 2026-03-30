"""Customer management endpoints via SQL Accounting API (SigV4)."""
import logging

from fastapi import APIRouter, HTTPException

from api.adapters import COMConnectionError
from api.clients import SqlAccountingApiError
from api.models import APIResponse, CustomerRequest
from api.services import COMOperationError, CustomerConfigurationError, CustomerService

router = APIRouter(prefix="/customers", tags=["Customers"])
logger = logging.getLogger(__name__)

customer_service = CustomerService()


@router.post("", response_model=APIResponse, status_code=201)
async def create_customer(customer_data: CustomerRequest):
    """Create customer via SQL Accounting REST API (AWS SigV4), not COM or direct SQL."""
    try:
        customer = customer_service.create_customer(customer_data)
        if customer.dry_run:
            state = {
                "skipped": True,
                "reason": "SQL_API_DRY_RUN: no remote create; post_create_state not read from COM.",
            }
        else:
            try:
                state = customer_service.get_customer_state(customer.code)
            except (COMOperationError, COMConnectionError) as exc:
                logger.warning("Post-create COM state read failed: %s", exc)
                state = {"error": str(exc), "source": "com"}
        return APIResponse(
            success=True,
            message="Customer created successfully (dry-run preview)"
            if customer.dry_run
            else "Customer created successfully",
            data={
                "customer": customer.model_dump(),
                "post_create_state": state,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CustomerConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except SqlAccountingApiError as exc:
        sc = exc.status_code
        if sc is None:
            raise HTTPException(status_code=503, detail=str(exc))
        if 400 <= sc < 500:
            raise HTTPException(status_code=422, detail=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Unhandled error while creating customer")
        raise HTTPException(status_code=500, detail=f"Failed to create customer: {str(exc)}")


@router.get("/{customer_code}/state", response_model=APIResponse)
async def get_customer_state(customer_code: str):
    """Read STATUS and SUBMISSIONTYPE for a customer code (COM read helper)."""
    try:
        state = customer_service.get_customer_state(customer_code)
        return APIResponse(
            success=True,
            message="Customer state retrieved successfully",
            data=state,
        )
    except COMConnectionError as exc:
        raise HTTPException(status_code=503, detail=f"COM connection failed: {str(exc)}")
    except COMOperationError as exc:
        raise HTTPException(status_code=422, detail=f"Failed to read customer state: {str(exc)}")
    except Exception as exc:
        logger.exception("Unhandled error while reading customer state")
        raise HTTPException(status_code=500, detail=f"Failed to read customer state: {str(exc)}")
