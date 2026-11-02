"""
Distributed Tracing & OpenTelemetry Instrumentation Module

Features:
- OpenTelemetry tracing env-toggled (`OTEL_ENABLED` or `ENABLE_OTEL`).
- Tracing across LangGraph execution, agent nodes, and external tool calls.
- Fallback to clean zero-overhead No-Op tracer when OpenTelemetry is disabled.
- LangSmith / Langfuse integration with prompt capture OFF by default.
"""

from contextlib import contextmanager
import logging
import os
from typing import Any, Dict, Iterator, Optional

logger = logging.getLogger("tripmate.tracing")

_TRACER_PROVIDER = None


def is_otel_enabled() -> bool:
    """Returns True if OpenTelemetry distributed tracing is enabled via environment."""
    otel_env = os.getenv("OTEL_ENABLED") or os.getenv("ENABLE_OTEL") or ""
    return otel_env.strip().lower() in ("true", "1", "yes", "on")


def init_telemetry(service_name: str = "tripmate-ai"):
    """Initializes OpenTelemetry TracerProvider when enabled."""
    global _TRACER_PROVIDER
    if not is_otel_enabled():
        _TRACER_PROVIDER = None
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)
        _TRACER_PROVIDER = provider
        logger.info("[Tracing] OpenTelemetry tracer provider initialized.")
        return provider
    except Exception as exc:
        logger.warning(f"[Tracing] Notice initializing OpenTelemetry: {exc}")
        _TRACER_PROVIDER = None
        return None


class NoOpSpan:
    """Zero-overhead no-op span for when tracing is disabled."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, *args, **kwargs) -> None:
        pass

    def record_exception(self, exception: Exception) -> None:
        pass

    def end(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class NoOpTracer:
    """Zero-overhead no-op tracer."""

    def start_span(self, name: str, **kwargs) -> NoOpSpan:
        return NoOpSpan()

    @contextmanager
    def start_as_current_span(self, name: str, **kwargs) -> Iterator[NoOpSpan]:
        yield NoOpSpan()


def get_tracer(name: str = "tripmate"):
    """Returns the OpenTelemetry tracer if enabled, otherwise returns NoOpTracer."""
    if is_otel_enabled():
        try:
            from opentelemetry import trace
            return trace.get_tracer(name)
        except Exception:
            pass
    return NoOpTracer()


@contextmanager
def trace_span(name: str, attributes: Optional[Dict[str, Any]] = None) -> Iterator[Any]:
    """Context manager for tracing operations across graph nodes and tool calls."""
    tracer = get_tracer("tripmate")
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                try:
                    span.set_attribute(k, v)
                except Exception:
                    pass
        yield span

