"""
Authentication & User Management Service

Handles registration, credential validation, token issuance, and user profiles.
"""

from typing import Any, Dict, Optional
from tripmate.database.store import store, hash_password, verify_password, generate_token
from tripmate.schemas import UserRegisterRequest, UserLoginRequest, TokenResponse, UserProfile


class AuthService:
    """Authentication and identity service."""

    def register_user(self, req: UserRegisterRequest) -> Dict[str, Any]:
        """Registers a new user account."""
        existing = store.get_user_by_username_or_email(req.username)
        if existing:
            raise ValueError(f"Username '{req.username}' is already registered.")

        existing_email = store.get_user_by_username_or_email(req.email)
        if existing_email:
            raise ValueError(f"Email '{req.email}' is already registered.")

        hashed_pw = hash_password(req.password)
        user = store.create_user(
            username=req.username,
            email=req.email,
            password_hash=hashed_pw,
            role=req.role,
        )
        token = generate_token(user["id"], user["username"], user["role"])
        return {
            "access_token": token,
            "token_type": "bearer",
            "user_id": user["id"],
            "username": user["username"],
            "role": user["role"],
        }

    def authenticate_user(self, req: UserLoginRequest) -> Dict[str, Any]:
        """Authenticates user credentials and returns an access token."""
        user = store.get_user_by_username_or_email(req.username_or_email)
        if not user or not verify_password(req.password, user["password_hash"]):
            raise ValueError("Invalid username/email or password.")

        token = generate_token(user["id"], user["username"], user["role"])
        return {
            "access_token": token,
            "token_type": "bearer",
            "user_id": user["id"],
            "username": user["username"],
            "role": user["role"],
        }

    def get_profile(self, user_id: str) -> Optional[UserProfile]:
        """Fetches user profile by user ID."""
        user = store.get_user_by_id(user_id)
        if not user:
            return None
        return UserProfile(
            id=user["id"],
            username=user["username"],
            email=user["email"],
            role=user["role"],
            created_at=user["created_at"],
        )


auth_service = AuthService()
