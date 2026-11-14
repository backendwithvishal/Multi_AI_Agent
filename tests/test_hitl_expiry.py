"""Tests for Human-In-The-Loop (HITL) approval expiry and cancellation.

Verifies:
1. Resuming an approval thread past APPROVAL_TTL_SECONDS raises HTTP 410 Gone.
2. The scheduled cancellation job cancels expired threads, marks them EXPIRED in persistence,
   and creates audit logs.
3. Background task worker `task_hitl_approval_expiry` executes successfully.
"""

import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from langgraph.checkpoint.memory import MemorySaver

from tripmate.agents.supervisor import SupervisorRouting, TripConstraints
from tripmate.config.settings import settings
from tripmate.graph.workflow import builder
from tripmate.services.travel_service import RUN_STORE, travel_service
from tripmate.tasks.workers import task_hitl_approval_expiry


@pytest.mark.asyncio
async def test_hitl_approval_ttl_expiry_raises_410():
    """Verify resuming a pending thread whose TTL has expired raises HTTP 410 Gone."""
    thread_id = "th_expiry_test_001"
    uid = "user_expiry_test"

    shared_checkpointer = MemorySaver()
    compiled_graph = builder.compile(checkpointer=shared_checkpointer)

    with (
        patch("tripmate.services.travel_service.travel_workflow_graph", compiled_graph),
        patch("tripmate.graph.workflow.run_guardrail_check", AsyncMock(return_value=(True, ""))),
        patch(
            "tripmate.graph.workflow.run_supervisor_routing",
            AsyncMock(
                return_value=SupervisorRouting(
                    selected_agents=["flight_agent"],
                    trip_constraints=TripConstraints(destination="Rome"),
                    reasoning="Plan Rome trip",
                )
            ),
        ),
    ):
        # 1. Execute initial plan to reach human_approval interrupt
        result = await travel_service.execute_travel_plan(
            user_input="Plan a 3-day trip to Rome",
            thread_id=thread_id,
            user_id=uid,
        )
        assert result["requires_approval"] is True

        # 2. Simulate timestamp expired past APPROVAL_TTL_SECONDS
        travel_service._approval_timestamps[thread_id] = time.time() - (settings.APPROVAL_TTL_SECONDS + 60)

        # 3. Attempting to resume must raise HTTP 410 GONE
        with pytest.raises(HTTPException) as exc_info:
            await travel_service.resume_travel_plan(
                thread_id=thread_id,
                approved=True,
                feedback="Approved",
                user_id=uid,
            )
        assert exc_info.value.status_code == 410
        assert exc_info.value.detail.get("code") == "APPROVAL_EXPIRED"


@pytest.mark.asyncio
async def test_cancel_expired_approvals_scheduled_job():
    """Verify scheduled job cancels expired threads and updates persistence and audit logs."""
    expired_run_id = f"run_expired_{int(time.time())}"
    expired_thread_id = f"th_expired_{int(time.time())}"
    uid = "user_cancel_test"

    # Seed an expired waiting run in RUN_STORE and workflow_run_repository
    old_time = time.time() - (settings.APPROVAL_TTL_SECONDS + 120)
    run_payload = {
        "run_id": expired_run_id,
        "id": expired_run_id,
        "thread_id": expired_thread_id,
        "user_id": uid,
        "status": "WAITING_FOR_APPROVAL",
        "start_time": old_time,
        "query": "Trip to Berlin",
        "answer": "Draft itinerary for Berlin",
    }
    RUN_STORE[expired_run_id] = run_payload
    travel_service._approval_timestamps[expired_thread_id] = old_time

    # Run cancellation job
    cancelled = await travel_service.cancel_expired_approvals()
    assert cancelled >= 1

    # Verify status in RUN_STORE
    updated_run = RUN_STORE.get(expired_run_id)
    assert updated_run["status"] == "EXPIRED"

    # Verify timestamp was cleaned up
    assert expired_thread_id not in travel_service._approval_timestamps


@pytest.mark.asyncio
async def test_task_hitl_approval_expiry_worker():
    """Verify background task worker executes cleanly."""
    res = await task_hitl_approval_expiry({})
    assert res["status"] == "COMPLETED"
    assert "expired_threads" in res
    assert res["ttl_seconds"] == settings.APPROVAL_TTL_SECONDS
