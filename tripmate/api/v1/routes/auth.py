"""
Authentication & User Management API Router

Endpoints:
- POST /api/v1/auth/register: Create a new user account
- POST /api/v1/auth/login: Authenticate and obtain JWT/bearer token
- GET /api/v1/auth/me: Retrieve current authenticated user profile
"""

from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request, status
from tripmate.schemas import (
    APIResponse,
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse,
    UserProfile,
    ErrorDetail,
)
from tripmate.services.auth_service import auth_service
from tripmate.api.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication & Identity"])


@router.post(
    "/register",
    summary="Register New User Account",
    description="Registers a new user and returns a signed bearer access token.",
    response_model=APIResponse[TokenResponse],
)
async def register(req: UserRegisterRequest, request: Request):
    request_id = getattr(request.state, "request_id", "req_auth")
    try:
        token_data = auth_service.register_user(req)
        return APIResponse(
            success=True,
            data=TokenResponse(**token_data),
            error=None,
            request_id=request_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "REGISTRATION_FAILED", "message": str(exc)},
        )


@router.post(
    "/login",
    summary="User Login",
    description="Authenticates credentials and returns a signed bearer access token.",
    response_model=APIResponse[TokenResponse],
)
async def login(req: UserLoginRequest, request: Request):
    request_id = getattr(request.state, "request_id", "req_auth")
    try:
        token_data = auth_service.authenticate_user(req)
        return APIResponse(
            success=True,
            data=TokenResponse(**token_data),
            error=None,
            request_id=request_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": str(exc)},
        )


@router.get(
    "/me",
    summary="Get Current User Profile",
    description="Retrieves profile information for the authenticated caller.",
    response_model=APIResponse[UserProfile],
)
async def get_me(request: Request, current_user: Dict[str, Any] = Depends(get_current_user)):
    request_id = getattr(request.state, "request_id", "req_auth")
    profile = auth_service.get_profile(current_user["id"])
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "User account could not be found."},
        )
    return APIResponse(
        success=True,
        data=profile,
        error=None,
        request_id=request_id,
    )
