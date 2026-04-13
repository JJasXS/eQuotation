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
    area: Optional[str] = Field(
        default=None,
        description="Area code",
        validation_alias=AliasChoices("area", "AREA"),
    )
    currency_code: Optional[str] = Field(
        default=None,
        description="Currency code",
        validation_alias=AliasChoices("currency_code", "currencycode", "CURRENCYCODE"),
    )
    tin: Optional[str] = Field(
        default=None,
        description="TIN",
        validation_alias=AliasChoices("tin", "TIN"),
    )
    brn: Optional[str] = Field(
        default=None,
        description="BRN",
        validation_alias=AliasChoices("brn", "BRN"),
    )
    brn2: Optional[str] = Field(
        default=None,
        description="BRN2",
        validation_alias=AliasChoices("brn2", "BRN2"),
    )
    sales_tax_no: Optional[str] = Field(
        default=None,
        description="Sales tax number",
        validation_alias=AliasChoices("sales_tax_no", "salestaxno", "SALESTAXNO"),
    )
    service_tax_no: Optional[str] = Field(
        default=None,
        description="Service tax number",
        validation_alias=AliasChoices("service_tax_no", "servicetaxno", "SERVICETAXNO"),
    )
    tax_exp_date: Optional[str] = Field(
        default=None,
        description="Tax expiry date",
        validation_alias=AliasChoices("tax_exp_date", "taxexpdate", "TAXEXPDATE"),
    )
    tax_exempt_no: Optional[str] = Field(
        default=None,
        description="Tax exempt number",
        validation_alias=AliasChoices("tax_exempt_no", "taxexemptno", "TAXEXEMPTNO"),
    )
    idtype: Optional[int] = Field(
        default=None,
        description="ID type",
        validation_alias=AliasChoices("idtype", "IDTYPE"),
    )
    attention: Optional[str] = Field(
        default=None,
        description="Attention name",
        validation_alias=AliasChoices("attention", "ATTENTION"),
    )
    address1: Optional[str] = Field(
        default=None,
        description="Address line 1",
        validation_alias=AliasChoices("address1", "ADDRESS1"),
    )
    address2: Optional[str] = Field(
        default=None,
        description="Address line 2",
        validation_alias=AliasChoices("address2", "ADDRESS2"),
    )
    address3: Optional[str] = Field(
        default=None,
        description="Address line 3",
        validation_alias=AliasChoices("address3", "ADDRESS3"),
    )
    address4: Optional[str] = Field(
        default=None,
        description="Address line 4",
        validation_alias=AliasChoices("address4", "ADDRESS4"),
    )
    postcode: Optional[str] = Field(
        default=None,
        description="Postcode",
        validation_alias=AliasChoices("postcode", "POSTCODE"),
    )
    city: Optional[str] = Field(
        default=None,
        description="City",
        validation_alias=AliasChoices("city", "CITY"),
    )
    state: Optional[str] = Field(
        default=None,
        description="State",
        validation_alias=AliasChoices("state", "STATE"),
    )
    country: Optional[str] = Field(
        default=None,
        description="Country",
        validation_alias=AliasChoices("country", "COUNTRY"),
    )
    phone: Optional[str] = Field(
        default=None,
        description="Phone number",
        validation_alias=AliasChoices("phone", "phone1", "PHONE1"),
    )
    email: Optional[str] = Field(
        default=None,
        description="Email",
        validation_alias=AliasChoices("email", "EMAIL"),
    )
    udf_email: Optional[str] = Field(
        default=None,
        description="User-defined email",
        validation_alias=AliasChoices("udf_email", "UDF_EMAIL"),
    )

    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "example": {
                "company_name": "ABC Sdn Bhd",
                "companyname": "ABC Sdn Bhd",
                "area": "PPS",
                "currencycode": "MYR",
                "tin": "2",
                "brn": "12",
                "brn2": "3",
                "salestaxno": "5",
                "servicetaxno": "6",
                "taxexpdate": "2025-02-21",
                "taxexemptno": "8",
                "idtype": 1,
                "attention": "John",
                "address1": "Line 1",
                "address2": "Line 2",
                "address3": "Line 3",
                "address4": "Line 4",
                "postcode": "50000",
                "city": "Kuala Lumpur",
                "state": "W.P. Kuala Lumpur",
                "country": "MY",
                "phone": "0123456789",
                "email": "abc@example.com",
                "udf_email": "abc@example.com"
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
    local_db_snapshot: Optional[dict[str, Any]] = Field(
        default=None,
        description="Verified local Firebird values after post-create sync.",
    )
