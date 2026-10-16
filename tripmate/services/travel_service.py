"""
High-Level Travel Planning Service Layer (Refactored with Patterns)

This service orchestrates all LangGraph workflow executions:
1. `execute_travel_plan`: Starts a new travel request thread or continues an existing one.
2. `resume_travel_plan`: Resumes a thread paused for Human-in-the-Loop (HITL) approval.
3. `stream_travel_events`: Generates Server-Sent Events (SSE) for real-time progress monitoring.
4. Maintains run history in memory for observability, metrics, and workflow replay APIs.

Architectural Patterns Applied:
- Builder Pattern: Uses TravelWorkflowStateBuilder & TravelPlanResponseBuilder.
- Observer Pattern: Emits strongly typed events through WorkflowEventDispatcher.
- Repository Pattern: Uses thread_owner_repository for thread ownership isolation.
- Singleton Pattern: Uses SingletonMeta.
"""

import json
import time
import uuid
from typing import Any, AsyncGenerator, Dict, Optional
from fastapi import HTTPException, status
# pyrefly: ignore [missing-import]
from langgraph.types import Command

from tripmate.api.dependencies import validate_thread_ownership
from tripmate.builders.response_builder import TravelPlanResponseBuilder
from tripmate.builders.workflow_state_builder import TravelWorkflowStateBuilder
from tripmate.core.singleton import SingletonMeta
from tripmate.database.store import store
from tripmate.events.dispatcher import workflow_dispatcher
from tripmate.events.events import (
    ApprovalRequiredEvent,
    CriticCompletedEvent,
    ItineraryCompletedEvent,
    SpecialistsCompletedEvent,
    SupervisorCompletedEvent,
    WorkflowCompletedEvent,
    WorkflowFailedEvent,
    WorkflowStartedEvent,
)
from tripmate.graph.workflow import travel_workflow_graph
from tripmate.repositories.interfaces import IThreadOwnerRepository
from tripmate.repositories.store_repositories import thread_owner_repository
from tripmate.services.observability import calculate_cost, estimate_tokens

# Global in-memory store for workflow run telemetry and replay history
RUN_STORE: Dict[str, Dict[str, Any]] = {}


def serialize_graph_result(result: Dict[str, Any], thread_id: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    """Formats internal graph dictionary into clean API response payload via TravelPlanResponseBuilder."""
    builder = TravelPlanResponseBuilder(result, thread_id).with_run_id(run_id)
    payload = builder.build()
    effective_run_id = payload["run_id"]
    RUN_STORE[effective_run_id] = payload
    return payload


class TravelService(metaclass=SingletonMeta):
    """Main service providing clean API interfaces for workflow invocation."""

    def __init__(self, owner_repo: Optional[IThreadOwnerRepository] = None):
        self._owner_repo = owner_repo or thread_owner_repository

    async def execute_travel_plan(
        self,
        user_input: str,
        thread_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Runs the complete multi-agent workflow for a travel query."""
        if not thread_id:
            thread_id = f"user_{uuid.uuid4().hex}"

        if user_id:
            await validate_thread_ownership(thread_id, user_id)
            self._owner_repo.register_owner(thread_id, user_id)

        run_id = f"run_{uuid.uuid4().hex[:12]}"
        config = {"configurable": {"thread_id": thread_id}}
        t0 = time.time()

        # Build validated LangGraph initial state using Builder pattern
        state_builder = (
            TravelWorkflowStateBuilder()
            .with_user_query(user_input)
            .with_thread_id(thread_id)
            .with_user_id(user_id)
            .with_run_id(run_id)
            .with_start_time(t0)
        )
        initial_state = state_builder.build()

        # Emit workflow started event via Observer pattern
        await workflow_dispatcher.publish(
            WorkflowStartedEvent(thread_id=thread_id, run_id=run_id, request_id=run_id)
        )

        try:
            result = await travel_workflow_graph.ainvoke(initial_state, config=config)
            serialized = serialize_graph_result(result, thread_id, run_id=run_id)

            await workflow_dispatcher.publish(
                WorkflowCompletedEvent(
                    thread_id=thread_id,
                    run_id=run_id,
                    success=True,
                    request_id=run_id,
                    result=serialized,
                )
            )
            return serialized
        except Exception as exc:
            await workflow_dispatcher.publish(
                WorkflowFailedEvent(
                    thread_id=thread_id,
                    run_id=run_id,
                    error=str(exc),
                    request_id=run_id,
                )
            )
            raise exc

    async def resume_travel_plan(
        self,
        thread_id: str,
        approved: bool,
        feedback: str = "",
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Resumes a paused workflow thread after human approval or revision request."""
        if user_id:
            await validate_thread_ownership(thread_id, user_id)

        config = {"configurable": {"thread_id": thread_id}}
        state = await travel_workflow_graph.aget_state(config)

        if not state or not getattr(state, "values", None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "THREAD_NOT_FOUND", "message": f"Thread ID '{thread_id}' not found or has no execution history."},
            )

        if not getattr(state, "next", None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_WORKFLOW_STATE", "message": f"Thread ID '{thread_id}' is not currently waiting for approval."},
            )

        result = await travel_workflow_graph.ainvoke(
            Command(
                resume={
                    "approved": approved,
                    "feedback": feedback.strip(),
                }
            ),
            config=config,
        )
        return serialize_graph_result(result, thread_id)

    async def stream_travel_events(
        self,
        user_input: str,
        thread_id: str,
        request_id: str,
        user_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Streams real-time execution progress events using Server-Sent Events (SSE)."""
        yield f"event: workflow.started\ndata: {json.dumps({'thread_id': thread_id, 'request_id': request_id, 'status': 'started'})}\n\n"

        if user_id:
            await validate_thread_ownership(thread_id, user_id)
            self._owner_repo.register_owner(thread_id, user_id)

        run_id = f"run_{uuid.uuid4().hex[:12]}"
        config = {"configurable": {"thread_id": thread_id}}
        t0 = time.time()

        # Build validated initial state using Builder pattern
        state_builder = (
            TravelWorkflowStateBuilder()
            .with_user_query(user_input)
            .with_thread_id(thread_id)
            .with_user_id(user_id)
            .with_run_id(run_id)
            .with_start_time(t0)
        )
        initial_input = state_builder.build()

        try:
            async for event in travel_workflow_graph.astream(initial_input, config=config, stream_mode="updates"):
                for node_name, node_output in event.items():
                    if node_name == "supervisor":
                        selected = node_output.get("selected_agents", [])
                        reasoning = node_output.get("supervisor_reasoning", "")
                        await workflow_dispatcher.publish(
                            SupervisorCompletedEvent(
                                thread_id=thread_id,
                                run_id=run_id,
                                selected_agents=selected,
                                reasoning=reasoning,
                            )
                        )
                        yield f"event: supervisor.completed\ndata: {json.dumps({'selected_agents': selected, 'reasoning': reasoning})}\n\n"
                    elif node_name == "parallel_specialists":
                        await workflow_dispatcher.publish(
                            SpecialistsCompletedEvent(thread_id=thread_id, run_id=run_id, node_name=node_name)
                        )
                        yield f"event: specialists.completed\ndata: {json.dumps({'status': 'completed', 'node': node_name})}\n\n"
                    elif node_name == "critic":
                        report = node_output.get("critic_report")
                        await workflow_dispatcher.publish(
                            CriticCompletedEvent(thread_id=thread_id, run_id=run_id, critic_report=report)
                        )
                        yield f"event: critic.completed\ndata: {json.dumps({'critic_report': report})}\n\n"
                    elif node_name == "itinerary_agent":
                        await workflow_dispatcher.publish(
                            ItineraryCompletedEvent(thread_id=thread_id, run_id=run_id)
                        )
                        yield f"event: itinerary.completed\ndata: {json.dumps({'status': 'draft_synthesized'})}\n\n"

            state = await travel_workflow_graph.aget_state(config)
            state_values = getattr(state, "values", {}) or {}
            serialized = serialize_graph_result(state_values, thread_id, run_id=run_id)

            if serialized.get("requires_approval"):
                await workflow_dispatcher.publish(
                    ApprovalRequiredEvent(
                        thread_id=thread_id,
                        run_id=run_id,
                        approval_request=serialized.get("approval_request", ""),
                    )
                )
                yield f"event: approval.required\ndata: {json.dumps({'approval_request': serialized.get('approval_request')})}\n\n"

            await workflow_dispatcher.publish(
                WorkflowCompletedEvent(
                    thread_id=thread_id,
                    run_id=run_id,
                    success=True,
                    request_id=request_id,
                    result=serialized,
                )
            )
            yield f"event: workflow.completed\ndata: {json.dumps({'success': True, 'request_id': request_id, **serialized})}\n\n"
        except Exception as exc:
            await workflow_dispatcher.publish(
                WorkflowFailedEvent(
                    thread_id=thread_id,
                    run_id=run_id,
                    error=str(exc),
                    request_id=request_id,
                )
            )
            yield f"event: workflow.failed\ndata: {json.dumps({'success': False, 'error': str(exc), 'request_id': request_id})}\n\n"


# Shared singleton instance
travel_service = TravelService()
