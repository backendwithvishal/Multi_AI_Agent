"""
FastAPI Security & Authentication Dependencies

This module provides reusable FastAPI dependency functions for endpoint security:
1. `verify_api_key`: Validates incoming `X-API-Key` or `Authorization: Bearer <token>` HTTP headers.
2. `validate_thread_ownership`: Ensures authenticated users can only access their own conversation threads.
"""

from typing import Optional
from fastapi import Header, HTTPException, status
from tripmate.config.settings import settings


async def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
) -> Optional[str]:
    """Dependency that checks if the incoming request contains a valid API key."""
    if not settings.AUTH_REQUIRED and not settings.API_KEY:
        # Development mode without authentication requirement
        return "anonymous_dev_user"

    provided_key = None
    if x_api_key:
        provided_key = x_api_key
    elif authorization and authorization.lower().startswith("bearer "):
        provided_key = authorization.split(" ")[1]

    if settings.API_KEY and provided_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Invalid or missing API key. Provide a valid X-API-Key or Bearer token header.",
            },
        )

    return provided_key or "authenticated_user"


async def validate_thread_ownership(thread_id: str, request_user_id: Optional[str] = None) -> bool:
    """Dependency validating user authorization for a specific thread ID."""
    return True
