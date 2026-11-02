"""
LLM Resilience Layer: Timeouts, Retries with Jitter, and Provider Circuit Breakers
"""

import asyncio
import logging
import random
from typing import Any, Callable, Dict, Optional

from tripmate.config.settings import settings
from tripmate.integrations.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenException,
    circuit_breaker_registry,
)

logger = logging.getLogger("tripmate.llm_resilience")

# Register Circuit Breakers for external LLM providers
groq_breaker = circuit_breaker_registry.register(
    CircuitBreaker("groq_llm", failure_threshold=3, cooldown_seconds=30.0)
)
openrouter_breaker = circuit_breaker_registry.register(
    CircuitBreaker("openrouter_llm", failure_threshold=3, cooldown_seconds=30.0)
)
huggingface_breaker = circuit_breaker_registry.register(
    CircuitBreaker("huggingface_llm", failure_threshold=3, cooldown_seconds=30.0)
)

PROVIDER_BREAKERS: Dict[str, CircuitBreaker] = {
    "groq": groq_breaker,
    "openrouter": openrouter_breaker,
    "huggingface": huggingface_breaker,
}


async def execute_with_backoff_and_jitter(
    coro_func: Callable[[], Any],
    max_retries: int = 1,
    base_delay: float = 0.5,
    max_delay: float = 2.5,
) -> Any:
    """Executes an async callable with bounded exponential backoff and randomized jitter."""
    for attempt in range(max_retries + 1):
        try:
            return await coro_func()
        except (CircuitBreakerOpenException, asyncio.CancelledError):
            raise
        except Exception as exc:
            if attempt >= max_retries:
                raise
            delay = min(max_delay, base_delay * (2**attempt))
            jitter = random.uniform(0.85, 1.15)
            sleep_time = delay * jitter
            logger.info(
                f"[LLM Retry] Attempt {attempt + 1}/{max_retries} failed ({exc}). Retrying in {sleep_time:.2f}s..."
            )
            await asyncio.sleep(sleep_time)


async def invoke_llm_with_resilience(
    llm: Any,
    messages: Any,
    provider_name: str = "groq",
    timeout: Optional[float] = None,
    max_retries: int = 1,
) -> Any:
    """Invokes LLM with per-call timeout, bounded retries, jitter, and circuit breaker."""
    if not llm:
        raise ValueError("No LLM client configured.")

    effective_timeout = timeout or settings.LLM_TIMEOUT_SECONDS
    breaker = PROVIDER_BREAKERS.get(provider_name.lower(), groq_breaker)

    async def _call():
        return await asyncio.wait_for(
            breaker.call(llm.ainvoke, messages),
            timeout=effective_timeout,
        )

    return await execute_with_backoff_and_jitter(_call, max_retries=max_retries)

