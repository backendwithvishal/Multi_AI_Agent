from fastapi import APIRouter, Request, Response, status
from tripmate.config.settings import settings
from tripmate.cache.redis_cache import hybrid_cache
from tripmate.database import check_db_health

router = APIRouter(tags=["System Health & Diagnostics"])


@router.get(
    "/health",
    summary="Detailed Health Telemetry",
    description="Returns detailed backend telemetry, feature list, and cache metrics.",
)
async def health_telemetry(request: Request):
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "request_id": getattr(request.state, "request_id", None),
        "features": [
            "supervisor_agent",
            "parallel_supervisor_agent",
            "pydantic_output_guardrail",
            "human_in_the_loop",
            "async_sse_streaming",
            "sliding_window_rate_limiter",
            "request_correlation_tracing",
            "bounded_ttl_mcp_caching",
            "circuit_breaker_resilience",
            "redis_hybrid_caching",
        ],
        "database": check_db_health(),
        "cache_stats": hybrid_cache.get_stats(),
    }


@router.get(
    "/liveness",
    summary="Process Liveness Probe",
    description="Liveness probe for Kubernetes and Docker container health monitors.",
)
async def liveness_probe():
    return {"status": "alive", "service": settings.APP_NAME}


@router.get(
    "/readiness",
    summary="Service Readiness Probe",
    description="Readiness probe verifying database connectivity and configuration readiness.",
)
async def readiness_probe(response: Response):
    db_health = check_db_health()
    if settings.APP_ENV == "production" and not db_health["connected"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "reason": "Database connection probe failed in production environment.",
            "database": db_health,
        }

    return {
        "status": "ready",
        "service": settings.APP_NAME,
        "database": db_health,
    }
