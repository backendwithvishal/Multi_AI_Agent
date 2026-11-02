"""
High-Level Travel Planning Service Layer (Refactored with Patterns & Reliability)

This service orchestrates all LangGraph workflow executions:
1. `execute_travel_plan`: Starts a new travel request thread or continues an existing one.
2. `resume_travel_plan`: Resumes a thread paused for Human-in-the-Loop (HITL) approval with TTL and idempotency.
3. `stream_travel_events`: Generates Server-Sent Events (SSE) with real graph updates, disconnect handling, and heartbeats.
4. Maintains run history in memory for observability, metrics, and workflow replay APIs.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Dict, Optional
from fastapi import HTTPException, Request, status
# pyrefly: ignore [missing-import]
from langgraph.types import Command

from tripmate.config.settings import settings
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

logger = logging.getLogger("tripmate.travel_service")

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
        self._approval_timestamps: Dict[str, float] = {}
        self._approval_history: Dict[str, Dict[str, Any]] = {}

    async def execute_travel_plan(
        self,
        user_input: str,
        thread_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Runs the complete multi-agent workflow for a travel query."""
        if not thread_id:
            thread_id = f"thread_{uuid.uuid4().hex}"

        if user_id:
            registered_owner = self._owner_repo.get_owner(thread_id)
            if registered_owner and registered_owner != user_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "THREAD_NOT_FOUND", "message": f"Thread '{thread_id}' not found."},
                )
            self._owner_repo.register_owner(thread_id, user_id)

        run_id = f"run_{uuid.uuid4().hex[:12]}"
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": settings.LANGGRAPH_RECURSION_LIMIT,
        }
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

            if serialized.get("requires_approval"):
                self._approval_timestamps[thread_id] = time.time()
                await workflow_dispatcher.publish(
                    ApprovalRequiredEvent(
                        thread_id=thread_id,
                        run_id=run_id,
                        approval_request=serialized.get("approval_request", ""),
                    )
                )

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
        """Resumes a paused workflow thread with TTL checks, state validation, and idempotent replay."""
        if user_id:
            await validate_thread_ownership(thread_id, user_id)

        # Idempotency check 1: cached in memory from previous resume invocation
        if thread_id in self._approval_history:
            return self._approval_history[thread_id]

        config = {"configurable": {"thread_id": thread_id}}
        state = await travel_workflow_graph.aget_state(config)

        if not state or not getattr(state, "values", None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "THREAD_NOT_FOUND", "message": f"Thread ID '{thread_id}' not found or has no execution history."},
            )

        # Idempotency check 2: if thread has already finished approval and completed
        state_values = getattr(state, "values", {}) or {}
        if not getattr(state, "next", None) and state_values.get("status") in ("APPROVED", "REVISION_REQUESTED", "COMPLETED"):
            serialized = serialize_graph_result(state_values, thread_id)
            self._approval_history[thread_id] = serialized
            return serialized

        # State check: a thread can only be resumed when currently interrupted at human_approval
        if not getattr(state, "next", None) or "human_approval" not in getattr(state, "next", ()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_WORKFLOW_STATE", "message": f"Thread ID '{thread_id}' is not currently waiting for approval."},
            )

        # TTL validation on pending approval
        created_at = self._approval_timestamps.get(thread_id) or state_values.get("approval_created_at")
        if created_at and (time.time() - created_at > settings.APPROVAL_TTL_SECONDS):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail={"code": "APPROVAL_EXPIRED", "message": f"Approval request for thread '{thread_id}' has expired."},
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
        serialized = serialize_graph_result(result, thread_id)
        # Store for idempotent subsequent calls
        self._approval_history[thread_id] = serialized
        self._approval_timestamps.pop(thread_id, None)
        return serialized

    async def stream_travel_events(
        self,
        user_input: str,
        thread_id: str,
        request_id: str,
        user_id: Optional[str] = None,
        request: Optional[Request] = None,
    ) -> AsyncGenerator[str, None]:
        """Streams real-time execution progress events using LangGraph async streaming (astream_events)."""
        current_task = asyncio.current_task()
        if current_task is not None:
            ACTIVE_RUNS.add(current_task)
            try:
                from tripmate.middleware.metrics import metrics_registry
                metrics_registry.inc_inflight_runs()
            except Exception:
                pass

        try:
            # Emit initial SSE heartbeat and start event
            yield ": heartbeat\n\n"
            yield f"event: workflow.started\ndata: {json.dumps({'thread_id': thread_id, 'request_id': request_id, 'status': 'started'})}\n\n"

            if user_id:
                registered_owner = await asyncio.to_thread(self._owner_repo.get_owner, thread_id)
                if registered_owner and registered_owner != user_id:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={"code": "THREAD_NOT_FOUND", "message": f"Thread '{thread_id}' not found."},
                    )
                await asyncio.to_thread(self._owner_repo.register_owner, thread_id, user_id)

            run_id = f"run_{uuid.uuid4().hex[:12]}"
            config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": settings.LANGGRAPH_RECURSION_LIMIT,
            }
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

            # Stream real-time LangGraph execution progress using astream_events v2
            async for event in travel_workflow_graph.astream_events(initial_input, config=config, version="v2"):
                # Handle client disconnect cancellation
                if request and await request.is_disconnected():
                    logger.info(f"Client disconnected. Cancelling graph run for thread '{thread_id}'.")
                    return

                yield ": heartbeat\n\n"

                ev_type = event.get("event")
                ev_name = event.get("name")
                data = event.get("data", {})

                # 1. Custom events: per-agent start and finish
                if ev_type == "on_custom_event":
                    if ev_name == "agent_started":
                        agent_name = data.get("agent", "specialist")
                        yield f"event: agent.started\ndata: {json.dumps(data)}\n\n"
                        yield f"event: {agent_name}.started\ndata: {json.dumps(data)}\n\n"
                    elif ev_name == "agent_finished":
                        agent_name = data.get("agent", "specialist")
                        yield f"event: agent.finished\ndata: {json.dumps(data)}\n\n"
                        yield f"event: {agent_name}.completed\ndata: {json.dumps(data)}\n\n"

                # 2. Node / step starts
                elif ev_type == "on_chain_start":
                    if ev_name in ("supervisor", "parallel_specialists", "critic", "itinerary_agent", "human_approval", "final_agent", "guardrail_blocked"):
                        yield f"event: step.update\ndata: {json.dumps({'step': ev_name, 'status': 'started'})}\n\n"
                        if ev_name == "parallel_specialists":
                            yield f"event: specialists.started\ndata: {json.dumps({'status': 'running'})}\n\n"

                # 3. Node / step completions & decisions
                elif ev_type == "on_chain_end":
                    if ev_name in ("supervisor", "parallel_specialists", "critic", "itinerary_agent", "human_approval", "final_agent", "guardrail_blocked"):
                        yield f"event: step.update\ndata: {json.dumps({'step': ev_name, 'status': 'completed'})}\n\n"
                        output_data = data.get("output")
                        if ev_name == "supervisor" and isinstance(output_data, dict):
                            selected = output_data.get("selected_agents", [])
                            reasoning = output_data.get("supervisor_reasoning", "")
                            await workflow_dispatcher.publish(
                                SupervisorCompletedEvent(
                                    thread_id=thread_id,
                                    run_id=run_id,
                                    selected_agents=selected,
                                    reasoning=reasoning,
                                )
                            )
                            yield f"event: supervisor.decision\ndata: {json.dumps({'selected_agents': selected, 'reasoning': reasoning})}\n\n"
                            yield f"event: supervisor.completed\ndata: {json.dumps({'selected_agents': selected, 'reasoning': reasoning})}\n\n"
                        elif ev_name == "parallel_specialists":
                            await workflow_dispatcher.publish(
                                SpecialistsCompletedEvent(thread_id=thread_id, run_id=run_id, node_name=ev_name)
                            )
                            yield f"event: specialists.completed\ndata: {json.dumps({'status': 'completed', 'node': ev_name})}\n\n"
                        elif ev_name == "critic" and isinstance(output_data, dict):
                            report = output_data.get("critic_report")
                            await workflow_dispatcher.publish(
                                CriticCompletedEvent(thread_id=thread_id, run_id=run_id, critic_report=report)
                            )
                            yield f"event: critic.completed\ndata: {json.dumps({'critic_report': report})}\n\n"
                        elif ev_name == "itinerary_agent":
                            await workflow_dispatcher.publish(
                                ItineraryCompletedEvent(thread_id=thread_id, run_id=run_id)
                            )
                            yield f"event: itinerary.completed\ndata: {json.dumps({'status': 'draft_synthesized'})}\n\n"

                # 4. Token streaming deltas
                elif ev_type == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        yield f"event: token\ndata: {json.dumps({'content': chunk.content})}\n\n"

            # Check for disconnect after graph execution loop
            if request and await request.is_disconnected():
                return

            # Read finalized or interrupted state from checkpointer
            state = await travel_workflow_graph.aget_state(config)
            state_values = getattr(state, "values", {}) or {}
            serialized = serialize_graph_result(state_values, thread_id, run_id=run_id)

            # Check if workflow reached Human-in-the-Loop interruption
            is_hitl = (
                serialized.get("requires_approval")
                or "human_approval" in getattr(state, "next", ())
                or state_values.get("status") == "WAITING_FOR_APPROVAL"
            )

            if is_hitl:
                self._approval_timestamps[thread_id] = time.time()
                await workflow_dispatcher.publish(
                    ApprovalRequiredEvent(
                        thread_id=thread_id,
                        run_id=run_id,
                        approval_request=serialized.get("approval_request", "Please review draft itinerary and approve or provide revision feedback."),
                    )
                )
                yield f"event: hitl_required\ndata: {json.dumps({'approval_request': serialized.get('approval_request')})}\n\n"
                yield f"event: approval.required\ndata: {json.dumps({'approval_request': serialized.get('approval_request')})}\n\n"

            # Publish completion and emit final results
            await workflow_dispatcher.publish(
                WorkflowCompletedEvent(
                    thread_id=thread_id,
                    run_id=run_id,
                    success=True,
                    request_id=request_id,
                    result=serialized,
                )
            )
            yield f"event: final_result\ndata: {json.dumps({'answer': serialized.get('answer'), 'itinerary': serialized.get('itinerary')})}\n\n"
            yield f"event: workflow.completed\ndata: {json.dumps({'success': True, 'request_id': request_id, **serialized})}\n\n"

        except asyncio.CancelledError:
            logger.info(f"Stream cancelled for thread '{thread_id}'.")
            return
        except Exception as exc:
            generic_err = f"Workflow error: {exc}"
            await workflow_dispatcher.publish(
                WorkflowFailedEvent(
                    thread_id=thread_id,
                    run_id=run_id,
                    error=str(exc),
                    request_id=request_id,
                )
            )
            yield f"event: error\ndata: {json.dumps({'code': 'WORKFLOW_ERROR', 'message': generic_err, 'request_id': request_id})}\n\n"
            yield f"event: workflow.failed\ndata: {json.dumps({'success': False, 'error': generic_err, 'request_id': request_id})}\n\n"
        finally:
            if current_task is not None:
                ACTIVE_RUNS.discard(current_task)
                try:
                    from tripmate.middleware.metrics import metrics_registry
                    metrics_registry.dec_inflight_runs()
                except Exception:
                    pass


# Active in-flight runs registry for graceful shutdown
ACTIVE_RUNS: set[asyncio.Task] = set()


# Shared singleton instance
travel_service = TravelService()
