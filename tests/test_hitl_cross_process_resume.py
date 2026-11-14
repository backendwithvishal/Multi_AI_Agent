"""Tests verifying cross-process Human-In-The-Loop (HITL) resumption.

Proves that a workflow thread paused at human_approval on Process/Instance A
can be resumed and completed on Process/Instance B via the shared checkpointer
without relying on any in-memory state on Process A.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.memory import MemorySaver

from app import app
from tripmate.agents.supervisor import SupervisorRouting, TripConstraints
from tripmate.database.store import generate_token, store
from tripmate.graph.workflow import builder
from tripmate.services.travel_service import TravelService


@pytest.mark.asyncio
async def test_cross_process_hitl_resume_via_shared_checkpointer():
    """Verify that Process B can resume a thread initiated and paused on Process A."""
    # Shared checkpointer simulating a persistent database (e.g. AsyncPostgresSaver / PostgreSQL)
    shared_checkpointer = MemorySaver()
    compiled_graph = builder.compile(checkpointer=shared_checkpointer)

    # Process A and Process B: two independent TravelService instances with separate in-memory caches

    service_process_a = TravelService.__new__(TravelService)
    service_process_a._store = store
    service_process_a._approval_timestamps = {}
    service_process_a._approval_history = {}

    service_process_b = TravelService.__new__(TravelService)
    service_process_b._store = store
    service_process_b._approval_timestamps = {}
    service_process_b._approval_history = {}

    thread_id = "th_cross_proc_001"
    uid = "user_cross_proc"

    # Mock the LLM routing and specialist outputs for determinism
    with (
        patch("tripmate.services.travel_service.travel_workflow_graph", compiled_graph),
        patch("tripmate.graph.workflow.run_guardrail_check", AsyncMock(return_value=(True, ""))),
        patch(
            "tripmate.graph.workflow.run_supervisor_routing",
            AsyncMock(
                return_value=SupervisorRouting(
                    selected_agents=["flight_agent", "weather_agent"],
                    trip_constraints=TripConstraints(destination="Tokyo"),
                    reasoning="Plan Tokyo trip",
                )
            ),
        ),
    ):
        # 1. Process A executes initial plan until interrupted at human_approval
        result_a = await service_process_a.execute_travel_plan(
            user_input="Plan a 5-day trip to Tokyo",
            thread_id=thread_id,
            user_id=uid,
        )

        assert result_a["requires_approval"] is True
        assert result_a["status"] == "WAITING_FOR_APPROVAL"
        assert thread_id in service_process_a._approval_timestamps

        # Assert Process B has NO local memory of this thread
        assert thread_id not in service_process_b._approval_timestamps
        assert thread_id not in service_process_b._approval_history

        # 2. Process B resumes the workflow using ONLY the shared checkpointer
        result_b = await service_process_b.resume_travel_plan(
            thread_id=thread_id,
            approved=True,
            feedback="Itinerary looks fantastic!",
            user_id=uid,
        )

        # 3. Workflow resumes from human_approval and executes final_node to completion
        assert result_b["status"] == "COMPLETED"
        assert result_b["approved"] is True
        assert result_b["human_feedback"] == "Itinerary looks fantastic!"
        assert "final_response" in result_b or "answer" in result_b

        # 4. Idempotency on Process B: repeating resume returns completed result
        replayed = await service_process_b.resume_travel_plan(
            thread_id=thread_id,
            approved=True,
            feedback="Itinerary looks fantastic!",
            user_id=uid,
        )
        assert replayed["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_api_route_travel_approve_hitl_resume():
    """Verify POST /api/v1/travel/approve successfully resumes a paused thread via HTTP API."""
    token = generate_token("user_hitl_api", "hitl_user", role="user")
    thread_id = "th_api_hitl_002"

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
                    trip_constraints=TripConstraints(destination="Paris"),
                    reasoning="Plan Paris trip",
                )
            ),
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Start travel plan
            start_res = await client.post(
                "/api/v1/travel",
                json={"message": "Trip to Paris", "thread_id": thread_id},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert start_res.status_code == 200
            start_data = start_res.json()["data"]
            assert start_data["requires_approval"] is True

            # 2. Approve travel plan via POST /api/v1/travel/approve
            approve_res = await client.post(
                "/api/v1/travel/approve",
                json={
                    "thread_id": thread_id,
                    "approved": True,
                    "feedback": "Approved, proceed with booking.",
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            assert approve_res.status_code == 200
            res_data = approve_res.json()
            assert res_data["success"] is True
            assert res_data["data"]["status"] == "COMPLETED"
            assert res_data["data"]["approved"] is True
