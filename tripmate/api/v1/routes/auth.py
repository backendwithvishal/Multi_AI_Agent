"""
Authentication & User Management API Router

Endpoints:
- POST /api/v1/auth/register: Create a new user account
- POST /api/v1/auth/login: Authenticate and obtain JWT/bearer token
- GET /api/v1/auth/me: Retrieve current authenticated user profile
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from tripmate.schemas import (
    APIResponse,
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse,
    UserProfile,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
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
async def register(
    req: UserRegisterRequest,
    request: Request,
    x_admin_secret: Optional[str] = Header(None, alias="X-Admin-Secret"),
):
    request_id = getattr(request.state, "request_id", "req_auth")
    try:
        token_data = auth_service.register_user(req, admin_secret=x_admin_secret)
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


@router.post(
    "/forgot-password",
    summary="Request Password Reset Token",
    description="Generates a single-use account recovery token with 15-minute expiration.",
    response_model=APIResponse[ForgotPasswordResponse],
)
async def forgot_password(req: ForgotPasswordRequest, request: Request):
    request_id = getattr(request.state, "request_id", "req_auth")
    result = auth_service.request_password_reset(req.email)
    return APIResponse(
        success=True,
        data=ForgotPasswordResponse(**result),
        error=None,
        request_id=request_id,
    )


@router.post(
    "/reset-password",
    summary="Reset Password with Recovery Token",
    description="Validates single-use token and sets new password.",
    response_model=APIResponse[Dict[str, Any]],
)
async def reset_password(req: ResetPasswordRequest, request: Request):
    request_id = getattr(request.state, "request_id", "req_auth")
    try:
        auth_service.reset_password(req.reset_token, req.new_password)
        return APIResponse(
            success=True,
            data={"message": "Password successfully updated. Please log in with your new credentials."},
            error=None,
            request_id=request_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_RESET_TOKEN", "message": str(exc)},
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
