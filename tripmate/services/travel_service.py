"""
High-Level Travel Planning Service Layer

This service orchestrates all LangGraph workflow executions:
1. `execute_travel_plan`: Starts a new travel request thread or continues an existing one.
2. `resume_travel_plan`: Resumes a thread paused for Human-in-the-Loop (HITL) approval.
3. `stream_travel_events`: Generates Server-Sent Events (SSE) for real-time progress monitoring.
4. Maintains run history in memory for observability, metrics, and workflow replay APIs.
"""

import json
import time
import uuid
from typing import Any, Dict, Optional, AsyncGenerator
from langchain_core.messages import HumanMessage
# pyrefly: ignore [missing-import]
from langgraph.types import Command

from tripmate.graph.workflow import travel_workflow_graph

# Global in-memory store for workflow run telemetry and replay history
RUN_STORE: Dict[str, Dict[str, Any]] = {}


def _interrupt_payload(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extracts Human-in-the-Loop interrupt payload if workflow is waiting for user review."""
    interrupts = result.get("__interrupt__", [])
    if not interrupts:
        return None
    first = interrupts[0]
    payload = getattr(first, "value", first)
    return payload if isinstance(payload, dict) else {"value": payload}


def serialize_graph_result(result: Dict[str, Any], thread_id: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    """Formats internal graph dictionary into clean API response payload."""
    messages = result.get("messages", [])
    last_message = messages[-1].content if messages else ""
    answer = result.get("final_response") or last_message
    interrupt_data = _interrupt_payload(result)

    if interrupt_data:
        answer = interrupt_data.get("draft_itinerary") or result.get("itinerary", "")

    effective_run_id = run_id or result.get("run_id") or f"run_{uuid.uuid4().hex[:12]}"

    payload = {
        "run_id": effective_run_id,
        "thread_id": thread_id,
        "status": result.get("status", "COMPLETED" if not interrupt_data else "WAITING_FOR_APPROVAL"),
        "answer": answer,
        "requires_approval": interrupt_data is not None,
        "approval_request": (
            interrupt_data.get("approval_request", "")
            if interrupt_data
            else result.get("approval_request", "")
        ),
        "flight_results": result.get("flight_results", ""),
        "hotel_results": result.get("hotel_results", ""),
        "weather_results": result.get("weather_results", ""),
        "budget_results": result.get("budget_results", ""),
        "itinerary": (
            interrupt_data.get("draft_itinerary", "")
            if interrupt_data
            else result.get("itinerary", "")
        ),
        "selected_agents": result.get("selected_agents", []),
        "trip_constraints": result.get("trip_constraints", {}),
        "supervisor_reasoning": result.get("supervisor_reasoning", ""),
        "guardrail_allowed": result.get("guardrail_allowed", True),
        "guardrail_reason": result.get("guardrail_reason", ""),
        "critic_report": result.get("critic_report"),
        "evidence_items": result.get("evidence_items", []),
        "structured_outputs": result.get("structured_outputs", {}),
        "approved": result.get("approved"),
        "human_feedback": result.get("human_feedback", ""),
        "llm_calls": result.get("llm_calls", 0),
        "metrics": result.get("metrics", {}),
    }

    RUN_STORE[effective_run_id] = payload
    return payload


from fastapi import HTTPException, status
from tripmate.database.store import store
from tripmate.api.dependencies import validate_thread_ownership


class TravelService:
    """Main service providing clean API interfaces for workflow invocation."""

    async def execute_travel_plan(self, user_input: str, thread_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Runs the complete multi-agent workflow for a travel query."""
        if not thread_id:
            thread_id = f"user_{uuid.uuid4().hex}"

        if user_id:
            await validate_thread_ownership(thread_id, user_id)
            store.register_thread_owner(thread_id, user_id)

        run_id = f"run_{uuid.uuid4().hex[:12]}"
        config = {"configurable": {"thread_id": thread_id}}
        t0 = time.time()

        result = await travel_workflow_graph.ainvoke(
            {
                "messages": [HumanMessage(content=user_input)],
                "user_query": user_input,
                "user_id": user_id,
                "thread_id": thread_id,
                "run_id": run_id,
                "status": "RUNNING",
                "guardrail_allowed": True,
                "guardrail_reason": "",
                "selected_agents": [],
                "trip_constraints": {},
                "supervisor_reasoning": "",
                "flight_results": "",
                "hotel_results": "",
                "weather_results": "",
                "budget_results": "",
                "itinerary": "",
                "approval_request": "",
                "approved": False,
                "human_feedback": "",
                "final_response": "",
                "structured_outputs": {},
                "evidence_items": [],
                "critic_report": {},
                "llm_calls": 0,
                "start_time": t0,
                "metrics": {"agent_latencies": {}, "total_latency_ms": 0.0},
            },
            config=config,
        )
        return serialize_graph_result(result, thread_id, run_id=run_id)

    async def resume_travel_plan(self, thread_id: str, approved: bool, feedback: str = "", user_id: Optional[str] = None) -> Dict[str, Any]:
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

    async def stream_travel_events(self, user_input: str, thread_id: str, request_id: str, user_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        """Streams real-time execution progress events using Server-Sent Events (SSE)."""
        yield f"event: workflow.started\ndata: {json.dumps({'thread_id': thread_id, 'request_id': request_id, 'status': 'started'})}\n\n"

        if user_id:
            await validate_thread_ownership(thread_id, user_id)
            store.register_thread_owner(thread_id, user_id)

        run_id = f"run_{uuid.uuid4().hex[:12]}"
        config = {"configurable": {"thread_id": thread_id}}
        t0 = time.time()
        initial_input = {
            "messages": [HumanMessage(content=user_input)],
            "user_query": user_input,
            "user_id": user_id,
            "thread_id": thread_id,
            "run_id": run_id,
            "status": "RUNNING",
            "guardrail_allowed": True,
            "guardrail_reason": "",
            "selected_agents": [],
            "trip_constraints": {},
            "supervisor_reasoning": "",
            "flight_results": "",
            "hotel_results": "",
            "weather_results": "",
            "budget_results": "",
            "itinerary": "",
            "approval_request": "",
            "approved": False,
            "human_feedback": "",
            "final_response": "",
            "structured_outputs": {},
            "evidence_items": [],
            "critic_report": {},
            "llm_calls": 0,
            "start_time": t0,
            "metrics": {"agent_latencies": {}, "total_latency_ms": 0.0},
        }

        try:
            async for event in travel_workflow_graph.astream(initial_input, config=config, stream_mode="updates"):
                for node_name, node_output in event.items():
                    if node_name == "supervisor":
                        selected = node_output.get("selected_agents", [])
                        reasoning = node_output.get("supervisor_reasoning", "")
                        yield f"event: supervisor.completed\ndata: {json.dumps({'selected_agents': selected, 'reasoning': reasoning})}\n\n"
                    elif node_name == "parallel_specialists":
                        yield f"event: specialists.completed\ndata: {json.dumps({'status': 'completed', 'node': node_name})}\n\n"
                    elif node_name == "critic":
                        yield f"event: critic.completed\ndata: {json.dumps({'critic_report': node_output.get('critic_report')})}\n\n"
                    elif node_name == "itinerary_agent":
                        yield f"event: itinerary.completed\ndata: {json.dumps({'status': 'draft_synthesized'})}\n\n"

            state = await travel_workflow_graph.aget_state(config)
            state_values = getattr(state, "values", {}) or {}
            serialized = serialize_graph_result(state_values, thread_id, run_id=run_id)

            if serialized.get("requires_approval"):
                yield f"event: approval.required\ndata: {json.dumps({'approval_request': serialized.get('approval_request')})}\n\n"

            yield f"event: workflow.completed\ndata: {json.dumps({'success': True, 'request_id': request_id, **serialized})}\n\n"
        except Exception as exc:
            yield f"event: workflow.failed\ndata: {json.dumps({'success': False, 'error': str(exc), 'request_id': request_id})}\n\n"


# Shared singleton instance
travel_service = TravelService()
