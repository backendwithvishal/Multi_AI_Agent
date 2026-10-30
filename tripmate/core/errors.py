"""
Structured Error Taxonomy & Standardized Error Responses
"""

from enum import Enum
from typing import Any, Dict, Optional


class ErrorCode(str, Enum):
    # Authentication & Authorization
    UNAUTHENTICATED = "UNAUTHENTICATED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    FORBIDDEN = "FORBIDDEN"
    ADMIN_REQUIRED = "ADMIN_REQUIRED"

    # Resource & Ownership
    NOT_FOUND = "NOT_FOUND"
    THREAD_NOT_FOUND = "THREAD_NOT_FOUND"
    THREAD_ACCESS_DENIED = "THREAD_ACCESS_DENIED"
    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"

    # Input & Validation
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    PROMPT_INJECTION_DETECTED = "PROMPT_INJECTION_DETECTED"
    INVALID_WORKFLOW_STATE = "INVALID_WORKFLOW_STATE"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"

    # Rate Limiting & Quotas
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    DAILY_TOKEN_BUDGET_EXCEEDED = "DAILY_TOKEN_BUDGET_EXCEEDED"

    # Provider & Downstream
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    CIRCUIT_BREAKER_OPEN = "CIRCUIT_BREAKER_OPEN"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    DEGRADED_OUTPUT = "DEGRADED_OUTPUT"

    # Server & Runtime
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    CHECKPOINTER_ERROR = "CHECKPOINTER_ERROR"
    CLIENT_DISCONNECTED = "CLIENT_DISCONNECTED"
    WORKFLOW_ERROR = "WORKFLOW_ERROR"
    TRAVEL_WORKFLOW_ERROR = "TRAVEL_WORKFLOW_ERROR"
    APPROVAL_WORKFLOW_ERROR = "APPROVAL_WORKFLOW_ERROR"
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    HTTP_ERROR = "HTTP_ERROR"


class AppException(Exception):
    """Base application exception with structured error code and HTTP status mapping."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self, request_id: Optional[str] = None) -> Dict[str, Any]:
        result = {
            "success": False,
            "error": {
                "code": self.code.value,
                "message": self.message,
            },
        }
        if self.details:
            result["error"]["details"] = self.details
        if request_id:
            result["request_id"] = request_id
        return result


class ThreadNotFoundException(AppException):
    def __init__(self, thread_id: str):
        super().__init__(
            code=ErrorCode.THREAD_NOT_FOUND,
            message=f"Thread '{thread_id}' not found.",
            status_code=404,
        )


class ApprovalExpiredException(AppException):
    def __init__(self, thread_id: str):
        super().__init__(
            code=ErrorCode.APPROVAL_EXPIRED,
            message=f"Approval request for thread '{thread_id}' has expired.",
            status_code=410,
        )


class InvalidWorkflowStateException(AppException):
    def __init__(self, thread_id: str, current_state: str = "completed"):
        super().__init__(
            code=ErrorCode.INVALID_WORKFLOW_STATE,
            message=f"Thread '{thread_id}' is not in an approval-pending state (current: {current_state}).",
            status_code=400,
        )


class ProviderTimeoutException(AppException):
    def __init__(self, provider_name: str, timeout_seconds: float):
        super().__init__(
            code=ErrorCode.PROVIDER_TIMEOUT,
            message=f"Provider '{provider_name}' timed out after {timeout_seconds}s.",
            status_code=504,
            details={"provider": provider_name, "timeout_seconds": timeout_seconds},
        )
