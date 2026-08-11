"""
FastAPI Security & Authentication Dependencies

This module provides reusable FastAPI dependency functions for endpoint security:
1. `verify_api_key`: Validates incoming `X-API-Key` or `Authorization: Bearer <token>` HTTP headers.
2. `get_current_user`: Resolves authenticated user profile from token or API key.
3. `require_admin`: Role-Based Access Control (RBAC) barrier requiring administrative privileges.
4. `validate_thread_ownership`: Ensures authenticated users can only access their own conversation threads.
"""

import secrets
from typing import Any, Dict, Optional
from fastapi import Header, HTTPException, status
from tripmate.config.settings import settings
from tripmate.database.store import store, verify_token


async def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
) -> str:
    """
    Validates that the incoming request contains an authentic API key.
    
    In development mode (AUTH_REQUIRED=false):
      - If no key is provided, allows anonymous development access.
      - If a key is provided, validates it against settings.API_KEY if configured.
      
    In production mode (AUTH_REQUIRED=true):
      - Rejects requests without an API key.
      - Validates key using constant-time string comparison.
    """
    provided_key: Optional[str] = None
    if x_api_key and x_api_key.strip():
        provided_key = x_api_key.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[1].strip():
            provided_key = parts[1].strip()

    expected_key = settings.API_KEY

    # Development mode without enforced authentication
    if not settings.AUTH_REQUIRED:
        if not provided_key:
            return "anonymous_dev_user"
        if expected_key and not secrets.compare_digest(provided_key, expected_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "UNAUTHORIZED",
                    "message": "Invalid API key provided. Provide a valid X-API-Key or Bearer token header.",
                },
            )
        return provided_key

    # Production / Enforced Authentication Mode
    if not provided_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Missing API key. Provide a valid X-API-Key or Bearer token header.",
            },
        )

    if expected_key and not secrets.compare_digest(provided_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Invalid API key provided.",
            },
        )

    return provided_key


async def get_current_user(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> Dict[str, Any]:
    """
    Resolves the authenticated user from Bearer Token or API Key.
    Returns user dictionary containing id, username, and role.
    """
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        parts = authorization.split(" ", 1)
        if len(parts) == 2:
            token = parts[1].strip()
    elif x_api_key and x_api_key.strip():
        token = x_api_key.strip()

    # 1. Try to decode signed session token
    if token:
        claims = verify_token(token)
        if claims:
            user = store.get_user_by_id(claims.get("uid", ""))
            if user:
                return user

    # 2. Check if master API_KEY was supplied
    if token and settings.API_KEY and secrets.compare_digest(token, settings.API_KEY):
        return {
            "id": "user_admin_001",
            "username": "admin",
            "email": "admin@tripmate.ai",
            "role": "admin",
        }

    # 3. If in development mode and no token provided, return demo user
    if not settings.AUTH_REQUIRED and not token:
        return {
            "id": "user_demo_002",
            "username": "demouser",
            "email": "user@tripmate.ai",
            "role": "admin" if not settings.AUTH_REQUIRED else "user",
        }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "UNAUTHORIZED",
            "message": "Authentication required. Provide a valid Bearer token or X-API-Key.",
        },
    )


async def require_admin(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> Dict[str, Any]:
    """RBAC dependency ensuring caller has administrative privileges."""
    user = await get_current_user(authorization=authorization, x_api_key=x_api_key)
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN",
                "message": "Administrative privileges required to access this resource.",
            },
        )
    return user


async def validate_thread_ownership(thread_id: str, request_user_id: Optional[str] = None) -> bool:
    """Validates user authorization and thread ownership for a specific thread ID."""
    if not thread_id or not request_user_id:
        return True

    registered_owner = store.get_thread_owner(thread_id)
    if registered_owner and registered_owner != request_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN",
                "message": f"User is not authorized to access or modify thread '{thread_id}'.",
            },
        )
    return True
