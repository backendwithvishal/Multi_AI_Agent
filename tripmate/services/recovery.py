"""
Failure Recovery & Resilience Layer

This module provides retry policies, exponential backoff, graceful degradation, and checkpoint recovery tools:
- `execute_with_retry`: Retries async operations with exponential backoff and jitter.
- `degrade_gracefully`: Converts catastrophic agent failures into safe degraded response payloads.
- `get_recoverable_checkpoint`: Inspects checkpoint history for resuming interrupted workflows.
"""

import asyncio
import random
import time
from typing import Any, Callable, Dict, Optional


async def execute_with_retry(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 2,
    initial_delay: float = 0.5,
    backoff_factor: float = 2.0,
    **kwargs: Any,
) -> Any:
    """Executes async function with exponential backoff retries."""
    delay = initial_delay
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return func(*args, **kwargs)
        except Exception as exc:
            last_exception = exc
            if attempt == max_retries:
                break
            # Add jitter to delay
            sleep_time = delay * (1 + random.uniform(0, 0.1))
            await asyncio.sleep(sleep_time)
            delay *= backoff_factor

    raise last_exception or RuntimeError("Execution failed after retries")


def degrade_gracefully(agent_name: str, exception: Exception) -> Dict[str, Any]:
    """Generates a structured fallback response when an agent unrecoverably fails."""
    return {
        "agent_name": agent_name,
        "status": "degraded",
        "result": f"Service notice ({agent_name}): Temporarily operating with degraded information due to downstream error.",
        "confidence": 0.3,
        "sources": [],
        "warnings": [f"Degraded recovery triggered: {str(exception)}"],
        "execution_time_ms": 0.0,
    }
