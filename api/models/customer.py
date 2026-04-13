"""Customer data models for SQL Account integration."""
from typing import Any, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class CustomerRequest(BaseModel):
    """Minimal request model for creating customer via SQL API."""

    code: Optional[str] = Field(default=None, min_length=1, description="Customer code")
    company_name: str = Field(
        ...,
        min_length=1,
        description="Company name",
        validation_alias=AliasChoices("company_name", "companyname"),
    )
    credit_term: str = Field(
        default="30 Days",
        min_length=1,
        description="Credit term",
        validation_alias=AliasChoices("credit_term", "creditterm"),
    )

    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "example": {
                "company_name": "ABC Sdn Bhd",
                "companyname": "ABC Sdn Bhd"
            }
        }
    )


class CustomerResponse(BaseModel):
    """Response model for customer create result."""

    code: str
    company_name: str
    credit_term: str
    saved: bool = True
    dry_run: bool = False
    request_preview: Optional[dict[str, Any]] = Field(
        default=None,
        description="When dry_run is True, the method/url/body that would have been sent.",
    )
    raw_response_snippet: Optional[str] = Field(
        default=None,
        description="Truncated raw HTTP body from the SQL Accounting API (debug).",
    )
    upstream_response: Optional[dict[str, Any]] = Field(
        default=None,
        description="Full parsed JSON body returned by SQL Accounting API.",
    )
