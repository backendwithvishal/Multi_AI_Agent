"""
Standard Background Task Workers

Implementations for:
1. Watchlist Price Scans (auto-evaluates threshold alerts)
2. Background Itinerary Generation & Asset Creation
3. System Health Audit Diagnostics
"""

import asyncio
import logging
from typing import Any, Dict
from decimal import Decimal

from tripmate.database.store import datastore
from tripmate.services.travel_service import travel_service
from tripmate.tasks.queue import task_queue

logger = logging.getLogger("tripmate.tasks.workers")


async def task_watchlist_price_scan(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Scans all active watchlists, evaluates threshold triggers, and produces alerts.
    """
    user_id = payload.get("user_id")
    all_watchlists = datastore.list_watchlists(user_id=user_id)
    watchlists = [w for w in all_watchlists if w.get("active", True)]
    scanned_count = len(watchlists)
    alerts_triggered = 0

    for wl in watchlists:
        # Simulate market price check (e.g. 5% price drop simulation)
        current_price = float(wl.get("current_price_estimate", 100.0))
        simulated_new_price = round(current_price * 0.92, 2)
        threshold = wl.get("threshold_price")

        if threshold is not None and simulated_new_price <= float(threshold):
            # Trigger alert
            datastore.create_alert(
                user_id=wl["user_id"],
                title=f"Price Drop Alert: {wl['title']}",
                message=(
                    f"Target price of ${float(threshold):.2f} reached! "
                    f"Current estimate dropped to ${simulated_new_price:.2f}."
                ),
                severity="success",
                watchlist_id=wl["id"],
            )
            alerts_triggered += 1

    return {
        "status": "COMPLETED",
        "scanned_watchlists": scanned_count,
        "alerts_triggered": alerts_triggered,
    }


async def task_background_itinerary(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes a comprehensive travel plan query in the background and saves it as a Travel Asset.
    """
    query = payload.get("query") or payload.get("message") or ""
    user_id = payload.get("user_id", "user_demo_002")
    thread_id = payload.get("thread_id")

    if not query.strip():
        raise ValueError("Missing 'query' or 'message' in background itinerary payload.")

    result = await travel_service.execute_travel_plan(
        user_input=query,
        thread_id=thread_id,
        user_id=user_id,
    )

    # Save generated itinerary as an asset if completed or waiting for approval
    if result.get("status") in ("COMPLETED", "WAITING_FOR_APPROVAL", "SUCCESS"):
        itinerary_text = result.get("itinerary") or result.get("answer") or ""
        asset = datastore.create_asset(
            user_id=user_id,
            name=f"Itinerary: {query[:50]}",
            asset_type="itinerary",
            metadata={
                "final_itinerary": itinerary_text,
                "run_id": result.get("run_id"),
                "status": result.get("status"),
            },
        )
        result["asset_id"] = asset["id"]

    return result


async def task_system_health_audit(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Performs platform health diagnostics across database, cache, and services.
    """
    from tripmate.database import check_db_health
    from tripmate.cache.redis_cache import hybrid_cache

    db_health = check_db_health()
    cache_health = await hybrid_cache.ping()

    return {
        "status": "COMPLETED",
        "database": db_health,
        "cache": {
            "connected": cache_health,
            "mode": "redis" if cache_health else "in-memory-fallback",
        },
        "system": "TripMate Multi-Agent Platform Active",
    }


# Auto-register standard task workers into task_queue
task_queue.register_handler("watchlist_price_scan", task_watchlist_price_scan)
task_queue.register_handler("background_itinerary", task_background_itinerary)
task_queue.register_handler("system_health_audit", task_system_health_audit)
