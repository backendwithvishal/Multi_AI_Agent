"""
Request Context & Correlation Tracking Module

Provides thread-safe and async-safe ContextVar storage for:
- Request correlation ID (`request_id` / `X-Request-ID`)
- Current authenticated user ID (`user_id`)
- Current conversation thread ID (`thread_id`)
- Cryptographic hashing of thread identifiers for safe logging
"""

import contextvars
import hashlib
from typing import Optional

# Async-safe request context variables
current_request_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_request_id", default=""
)
current_user_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_user_id", default=None
)
current_thread_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_thread_id", default=None
)


def set_request_context(
    request_id: str,
    user_id: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> None:
    """Sets the active request context for the current async task execution chain."""
    current_request_id.set(request_id)
    if user_id is not None:
        current_user_id.set(user_id)
    if thread_id is not None:
        current_thread_id.set(thread_id)


def get_request_id() -> str:
    """Returns the current request_id, or an empty string if outside request scope."""
    return current_request_id.get() or ""


def get_user_id() -> Optional[str]:
    """Returns the current authenticated user_id if set."""
    return current_user_id.get()


def get_thread_id() -> Optional[str]:
    """Returns the current active thread_id if set."""
    return current_thread_id.get()


def hash_thread_id(thread_id: Optional[str]) -> Optional[str]:
    """
    Computes a deterministic SHA-256 hash of a thread_id.
    Prevents raw conversational or session identifiers from leaking into production logs.
    """
    if not thread_id:
        return None
    digest = hashlib.sha256(thread_id.strip().encode("utf-8")).hexdigest()
    return f"th_hash_{digest[:16]}"

