"""Customer management endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from api.models import APIResponse, CustomerRequest, CustomerResponse
from api.services import CustomerService
from api.auth import validate_api_key

router = APIRouter(prefix="/customers", tags=["Customers"])

# Initialize service
customer_service = CustomerService()


@router.post("", response_model=APIResponse, status_code=201)
async def create_customer(
    customer_data: CustomerRequest,
    credentials: dict = Depends(validate_api_key)
):
    """
    Create a new customer.
    
    **Required Headers:**
    - X-Access-Key: API access key
    - X-Secret-Key: API secret key
    
    **Request Body:**
    - companyName (required): Customer company name
    - phone1 (required): Customer phone number
    - email (required): Customer email address
    - address1 (required): Street address
    - Other fields optional
    
    Returns:
        Created customer data
    """
    try:
        customer = customer_service.create_customer(customer_data)
        return APIResponse(
            success=True,
            message="Customer created successfully",
            data=customer.dict()
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create customer: {str(e)}"
        )


@router.get("/{customer_code}", response_model=APIResponse)
async def get_customer(
    customer_code: str,
    credentials: dict = Depends(validate_api_key)
):
    """
    Get customer details by customer code.
    
    **Required Headers:**
    - X-Access-Key: API access key
    - X-Secret-Key: API secret key
    
    **Path Parameters:**
    - customer_code: Customer code (e.g., 300-E0001)
    
    Returns:
        Customer data or error if not found
    """
    try:
        customer = customer_service.get_customer(customer_code)
        if not customer:
            raise HTTPException(
                status_code=404,
                detail=f"Customer {customer_code} not found"
            )
        
        return APIResponse(
            success=True,
            message="Customer retrieved successfully",
            data=customer.dict()
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve customer: {str(e)}"
        )


@router.put("/{customer_code}", response_model=APIResponse)
async def update_customer(
    customer_code: str,
    customer_data: CustomerRequest,
    credentials: dict = Depends(validate_api_key)
):
    """
    Update an existing customer.
    
    **Required Headers:**
    - X-Access-Key: API access key
    - X-Secret-Key: API secret key
    
    **Path Parameters:**
    - customer_code: Customer code to update
    
    **Request Body:**
    - Updated customer fields
    
    Returns:
        Updated customer data
    """
    try:
        customer = customer_service.update_customer(customer_code, customer_data)
        return APIResponse(
            success=True,
            message="Customer updated successfully",
            data=customer.dict()
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update customer: {str(e)}"
        )


@router.delete("/{customer_code}", response_model=APIResponse)
async def delete_customer(
    customer_code: str,
    credentials: dict = Depends(validate_api_key)
):
    """
    Delete a customer (if allowed by permissions).
    
    **Required Headers:**
    - X-Access-Key: API access key
    - X-Secret-Key: API secret key
    
    **Path Parameters:**
    - customer_code: Customer code to delete
    
    Returns:
        Success or error message
    """
    try:
        success = customer_service.delete_customer(customer_code)
        return APIResponse(
            success=success,
            message="Customer deleted successfully" if success else "Failed to delete customer",
            data={"customerCode": customer_code}
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete customer: {str(e)}"
        )
