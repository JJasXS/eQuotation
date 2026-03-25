"""Customer data models."""
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class CustomerRequest(BaseModel):
    """Request model for creating/updating a customer."""
    companyCode: Optional[str] = None
    customerCode: Optional[str] = None
    companyName: str = Field(..., min_length=1, description="Company name is required")
    phone1: str = Field(..., min_length=1, description="Phone number is required")
    email: EmailStr = Field(..., description="Valid email is required")
    address1: str = Field(..., min_length=1, description="Address is required")
    address2: Optional[str] = None
    address3: Optional[str] = None
    address4: Optional[str] = None
    postcode: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None

    class Config:
        example = {
            "companyCode": "300-000",
            "customerCode": "300-E0001",
            "companyName": "Acme Corporation",
            "phone1": "0123456789",
            "email": "contact@acme.com",
            "address1": "123 Main Street",
            "address2": "Suite 100",
            "postcode": "50000",
            "city": "Kuala Lumpur",
            "state": "Federal Territory",
            "country": "Malaysia"
        }


class CustomerResponse(BaseModel):
    """Response model for customer data."""
    customerCode: str
    companyName: str
    phone1: str
    email: str
    address1: str
    address2: Optional[str] = None
    address3: Optional[str] = None
    address4: Optional[str] = None
    postcode: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None

    class Config:
        example = {
            "customerCode": "300-E0001",
            "companyName": "Acme Corporation",
            "phone1": "0123456789",
            "email": "contact@acme.com",
            "address1": "123 Main Street",
            "postcode": "50000",
            "city": "Kuala Lumpur"
        }
