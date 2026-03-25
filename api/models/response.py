"""Standard API response models."""
from typing import Any, Optional, List
from pydantic import BaseModel


class APIResponse(BaseModel):
    """Standard API response format for all endpoints."""
    success: bool
    message: str
    data: Optional[Any] = None
    errors: Optional[List[str]] = None

    class Config:
        example = {
            "success": True,
            "message": "Request successful",
            "data": {},
            "errors": None
        }
