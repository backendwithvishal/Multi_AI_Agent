from typing import Any, Generic, Optional, TypeVar
from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str = Field(description="Machine-readable error classification code.")
    message: str = Field(description="Human-readable error summary message.")
    details: Optional[Any] = Field(default=None, description="Optional extra diagnostic details.")


class APIResponse(BaseModel, Generic[T]):
    success: bool = Field(description="Indicates successful execution.")
    data: Optional[T] = Field(default=None, description="Response payload data when successful.")
    error: Optional[ErrorDetail] = Field(default=None, description="Error detail container when unsuccessful.")
    request_id: str = Field(description="Unique correlation ID attached to request.")


class TravelRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The user's travel planning request or query.",
    )
    thread_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional unique identifier for continuing an existing conversation thread.",
    )
    user_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional identity string for authorization and thread ownership validation.",
    )

    @field_validator("message")
    @classmethod
    def validate_message_not_whitespace(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Message cannot consist only of whitespace.")
        return cleaned


class ApprovalRequest(BaseModel):
    thread_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Required thread ID of the paused execution graph.",
    )
    approved: bool = Field(
        ...,
        description="True to finalize the plan; False to request revisions.",
    )
    feedback: str = Field(
        default="",
        max_length=1000,
        description="Optional feedback instructions for revisions when rejected.",
    )
    user_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional identity string for authorization and thread ownership validation.",
    )

    @field_validator("feedback")
    @classmethod
    def validate_feedback(cls, v: str) -> str:
        return v.strip()
