"""Customer data models for SQL Account COM API."""
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CustomerRequest(BaseModel):
    """Request model for creating customer via COM."""

    code: str = Field(..., min_length=1, description="Customer code")
    company_name: str = Field(..., min_length=1, description="Company name")
    credit_term: str = Field(..., min_length=1, description="Credit term")
    control_account: str = Field(default="300-000", description="Control account")
    company_category: str = Field(default="----", description="Company category")
    area: Optional[str] = Field(default=None, description="Area code")
    agent: str = Field(default="----", description="Agent code")
    statement_type: str = Field(default="O", description="Statement type")
    currency_code: Optional[str] = Field(default=None, description="Currency code")
    aging_on: str = Field(default="I", description="Aging mode")
    status: str = Field(default="A", description="Customer status")
    submission_type: Optional[str] = Field(default=None, description="Submission type")
    brn: Optional[str] = Field(default=None, description="Business registration number")
    brn2: Optional[str] = Field(default=None, description="Business registration number 2")
    tin: Optional[str] = Field(default=None, description="TIN")
    sales_tax_no: Optional[str] = Field(default=None, description="Sales tax number")
    service_tax_no: Optional[str] = Field(default=None, description="Service tax number")
    tax_exempt_no: Optional[str] = Field(default=None, description="Tax exempt number")
    tax_exp_date: Optional[str] = Field(default=None, description="Tax expiry date")
    udf_email: Optional[str] = Field(default=None, description="User-defined email")
    attachments: Optional[str] = Field(default=None, description="Attachment path or reference")
    phone: Optional[str] = Field(default=None, description="Primary phone")
    phone2: Optional[str] = Field(default=None, description="Secondary phone")
    mobile: Optional[str] = Field(default=None, description="Mobile phone")
    fax1: Optional[str] = Field(default=None, description="Fax 1")
    fax2: Optional[str] = Field(default=None, description="Fax 2")
    email: Optional[str] = Field(default=None, description="Branch email")
    branch_type: str = Field(default="B", description="Branch type")
    branch_name: str = Field(default="BILLING", description="Branch name")
    branch_dtlkey: Optional[str] = Field(default=None, description="Branch DTLKEY override")
    attention: Optional[str] = Field(default=None, description="Branch attention")
    address1: Optional[str] = Field(default=None, description="Address line 1")
    address2: Optional[str] = Field(default=None, description="Address line 2")
    address3: Optional[str] = Field(default=None, description="Address line 3")
    address4: Optional[str] = Field(default=None, description="Address line 4")
    postcode: Optional[str] = Field(default=None, description="Postcode")
    city: Optional[str] = Field(default=None, description="City")
    state: Optional[str] = Field(default=None, description="State")
    country: Optional[str] = Field(default=None, description="Country")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "CUST001",
                "company_name": "ABC Sdn Bhd",
                "credit_term": "30 Days",
                "control_account": "300-000",
                "area": "KL",
                "currency_code": "----",
                "brn": "TEST123456789",
                "udf_email": "test@example.com",
                "phone": "0123456789",
                "address1": "Address line 1",
                "postcode": "50000",
                "attention": "PIC Name",
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
