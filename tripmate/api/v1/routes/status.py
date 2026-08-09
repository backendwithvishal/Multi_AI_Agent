"""
System Status & Operational Diagnostics API Router

Endpoint:
- GET /api/v1/status: Operational telemetry, agent registry availability, circuit breakers, cache backend
"""

from fastapi import APIRouter, Request
from tripmate.config.settings import settings
from tripmate.agents.registry import agent_registry
from tripmate.integrations.mcp import tavily_breaker, aviation_breaker, weather_breaker
from tripmate.cache.redis_cache import hybrid_cache
from tripmate.database.store import store
from tripmate.schemas import APIResponse, SystemStatusResponse

router = APIRouter(tags=["System Status & Diagnostics"])


@router.get(
    "/status",
    summary="System Operational Status",
    description="Returns real-time operational status of backend services, agents, circuit breakers, and cache.",
    response_model=APIResponse[SystemStatusResponse],
)
async def get_system_status(request: Request):
    request_id = getattr(request.state, "request_id", "req_status")
    
    agent_names = [a.name for a in agent_registry.list_agents()] or [
        "flight_agent",
        "hotel_agent",
        "weather_agent",
        "budget_agent",
        "itinerary_agent",
    ]

    breakers = {
        tavily_breaker.name: tavily_breaker.state.value,
        aviation_breaker.name: aviation_breaker.state.value,
        weather_breaker.name: weather_breaker.state.value,
    }

    cache_stats = hybrid_cache.get_stats()

    status_data = SystemStatusResponse(
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
        uptime_seconds=store.get_system_uptime(),
        status="OPERATIONAL",
        circuit_breakers=breakers,
        agent_registry=agent_names,
        model_tiers={
            "groq_configured": bool(settings.GROQ_API_KEY),
            "openrouter_configured": bool(settings.OPENROUTER_API_KEY),
        },
        cache_backend=cache_stats.get("backend", "in_memory"),
    )

    return APIResponse(
        success=True,
        data=status_data,
        error=None,
        request_id=request_id,
    )
