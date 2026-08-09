"""
Admin Domain Management Service

Handles administrative telemetry aggregation, user list, circuit breaker manual resets, and cache clearing.
"""

from typing import Any, Dict, List
from tripmate.database.store import store
from tripmate.services.travel_service import RUN_STORE
from tripmate.cache.redis_cache import hybrid_cache
from tripmate.integrations.mcp import tavily_breaker, aviation_breaker, weather_breaker
from tripmate.config.settings import settings


class AdminService:
    """Service providing platform administrator operations."""

    def get_platform_stats(self) -> Dict[str, Any]:
        """Aggregates platform statistics across all domains."""
        users = store.list_users()
        watchlists = store.list_watchlists()
        alerts = store.list_alerts()
        assets = store.list_assets()

        breakers = {
            tavily_breaker.name: tavily_breaker.state.value,
            aviation_breaker.name: aviation_breaker.state.value,
            weather_breaker.name: weather_breaker.state.value,
        }

        return {
            "total_users": len(users),
            "total_runs": len(RUN_STORE),
            "total_watchlists": len(watchlists),
            "total_alerts": len(alerts),
            "total_assets": len(assets),
            "circuit_breakers": breakers,
            "cache_stats": hybrid_cache.get_stats(),
            "active_environment": settings.APP_ENV,
        }

    def list_all_users(self) -> List[Dict[str, Any]]:
        """Returns safe user summaries."""
        users = store.list_users()
        return [
            {
                "id": u["id"],
                "username": u["username"],
                "email": u["email"],
                "role": u["role"],
                "created_at": u["created_at"],
            }
            for u in users
        ]

    def reset_circuit_breaker(self, service_name: str) -> Dict[str, Any]:
        """Manually resets designated circuit breakers."""
        reset_list = []
        if service_name in (tavily_breaker.name, "all"):
            tavily_breaker.reset()
            reset_list.append(tavily_breaker.name)
        if service_name in (aviation_breaker.name, "all"):
            aviation_breaker.reset()
            reset_list.append(aviation_breaker.name)
        if service_name in (weather_breaker.name, "all"):
            weather_breaker.reset()
            reset_list.append(weather_breaker.name)

        return {
            "reset_breakers": reset_list,
            "status": "CLOSED",
            "message": f"Successfully reset {', '.join(reset_list)} circuit breakers.",
        }

    async def clear_cache(self) -> Dict[str, Any]:
        """Clears platform cache."""
        await hybrid_cache.clear()
        return {"status": "cleared", "message": "Platform cache cleared successfully."}


admin_service = AdminService()
