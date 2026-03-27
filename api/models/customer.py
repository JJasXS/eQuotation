"""Customer data models for SQL Account COM API."""
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CustomerRequest(BaseModel):
    """Request model for creating customer via COM."""

    code: str = Field(..., min_length=1, description="Customer code")
    company_name: str = Field(..., min_length=1, description="Company name")
    credit_term: str = Field(..., min_length=1, description="Credit term")
    phone: Optional[str] = Field(default=None, description="Primary phone")
    address1: Optional[str] = Field(default=None, description="Address line 1")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "CUST001",
                "company_name": "ABC Sdn Bhd",
                "credit_term": "30",
                "phone": "0123456789",
                "address1": "Address line 1",
            }
        }
    )


class CustomerResponse(BaseModel):
    """Response model for customer create result."""

    code: str
    company_name: str
    credit_term: str
    phone: Optional[str] = None
    address1: Optional[str] = None
    saved: bool = True
