"""
Decorator Pattern Implementation

Provides reusable decorators for cross-cutting concerns:
1. `timed_async`: Tracks and records asynchronous execution latency.
2. `retry_async`: Applies configurable exponential backoff retry policies for transient errors.
3. `circuit_protected`: Guards asynchronous operations with a circuit breaker.

All decorators strictly preserve function signatures, type annotations, and docstrings
using `functools.wraps`.
"""

import asyncio
import functools
import logging
import time
from typing import Any, Callable, Coroutine, Dict, Optional, Tuple, Type, Union

logger = logging.getLogger("tripmate.decorators")


def timed_async(
    metric_name: Optional[str] = None,
    log_level: int = logging.DEBUG,
    metrics_target: Optional[Dict[str, Any]] = None,
) -> Callable:
    """
    Decorator measuring execution duration of an async function.
    Records duration in milliseconds and optionally logs or updates a metrics dictionary.
    """
    def decorator(func: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Coroutine[Any, Any, Any]]:
        name = metric_name or func.__name__

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                logger.log(log_level, f"[TIMING] {name} completed in {elapsed_ms}ms")
                if metrics_target is not None and isinstance(metrics_target, dict):
                    metrics_target[name] = elapsed_ms
        return wrapper
    return decorator


def retry_async(
    max_retries: int = 3,
    base_delay: float = 0.5,
    backoff_factor: float = 2.0,
    retryable_exceptions: Tuple[Type[BaseException], ...] = (
        asyncio.TimeoutError,
        ConnectionError,
        TimeoutError,
    ),
) -> Callable:
    """
    Decorator applying exponential backoff retries to an async function.
    Only catches designated retryable exceptions (transient failures). Permanent failures
    (e.g. ValueError, KeyError, authentication errors) immediately re-raise without retrying.
    """
    def decorator(func: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Coroutine[Any, Any, Any]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            attempt = 0
            delay = base_delay
            while True:
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as exc:
                    attempt += 1
                    if attempt > max_retries:
                        logger.warning(
                            f"[RETRY EXHAUSTED] {func.__name__} failed after {max_retries} retries: {exc}"
                        )
                        raise
                    logger.info(
                        f"[RETRY] {func.__name__} transient failure ({exc}), retry {attempt}/{max_retries} in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                    delay *= backoff_factor
        return wrapper
    return decorator


def circuit_protected(breaker: Any) -> Callable:
    """
    Decorator guarding an async callable with a CircuitBreaker instance.
    """
    def decorator(func: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Coroutine[Any, Any, Any]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await breaker.call(func, *args, **kwargs)
        return wrapper
    return decorator
