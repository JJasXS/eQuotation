"""API authentication utilities."""
import os
from fastapi import HTTPException, Header
from typing import Optional


# Auth config (read from environment)
API_ACCESS_KEY = os.getenv('API_ACCESS_KEY', 'default-access-key')
API_SECRET_KEY = os.getenv('API_SECRET_KEY', 'default-secret-key')


def validate_api_key(
    x_access_key: Optional[str] = Header(None),
    x_secret_key: Optional[str] = Header(None)
) -> dict:
    """
    Validate API credentials from X-Access-Key and X-Secret-Key headers.
    
    Args:
        x_access_key: API access key from X-Access-Key header
        x_secret_key: API secret key from X-Secret-Key header
    
    Returns:
        dict with validated credentials
        
    Raises:
        HTTPException: If credentials are invalid
    """
    if not x_access_key or not x_secret_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-Access-Key or X-Secret-Key headers"
        )
    
    # Simple string comparison (In production, use more secure methods like JWT or OAuth2)
    if x_access_key != API_ACCESS_KEY or x_secret_key != API_SECRET_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API credentials"
        )
    
    return {"access_key": x_access_key}
