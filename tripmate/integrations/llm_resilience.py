"""
LLM Resilience Layer: Timeouts, Retries with Jitter, and Provider Circuit Breakers
"""

import asyncio
import logging
import random
from typing import Any, Callable, Dict, Optional

from tripmate.config.settings import settings
from tripmate.core.context import get_request_id
from tripmate.middleware.metrics import metrics_registry
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

    req_id = get_request_id() or ""
    call_config = {
        "metadata": {"request_id": req_id},
        "configurable": {"request_id": req_id},
        "tags": [f"request_id:{req_id}"] if req_id else [],
    }

    # Inject X-Request-ID into LLM client default headers if supported
    if req_id and hasattr(llm, "default_headers") and isinstance(llm.default_headers, dict):
        llm.default_headers["X-Request-ID"] = req_id

    async def _call():
        try:
            res = await asyncio.wait_for(
                breaker.call(llm.ainvoke, messages, config=call_config),
                timeout=effective_timeout,
            )
        except TypeError:
            # Fallback if mock or client doesn't accept config
            res = await asyncio.wait_for(
                breaker.call(llm.ainvoke, messages),
                timeout=effective_timeout,
            )

        # Record LLM token metrics if available
        try:
            model_name = (
                getattr(llm, "model_name", None)
                or getattr(llm, "model", None)
                or provider_name
            )
            usage = None
            if hasattr(res, "usage_metadata") and res.usage_metadata:
                usage = res.usage_metadata
                prompt_tokens = usage.get("input_tokens", 0)
                completion_tokens = usage.get("output_tokens", 0)
            elif hasattr(res, "response_metadata") and isinstance(res.response_metadata, dict):
                meta_usage = res.response_metadata.get("token_usage") or res.response_metadata.get("usage") or {}
                prompt_tokens = meta_usage.get("prompt_tokens", 0)
                completion_tokens = meta_usage.get("completion_tokens", 0)
            else:
                prompt_tokens, completion_tokens = 0, 0

            if prompt_tokens > 0 or completion_tokens > 0:
                metrics_registry.record_llm_tokens(model_name, prompt_tokens, completion_tokens)
        except Exception as exc:
            logger.debug(f"[LLM Metrics Notice] Could not parse token usage: {exc}")

        return res

    return await execute_with_backoff_and_jitter(_call, max_retries=max_retries)

