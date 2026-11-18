"""
High-Level Travel Planning Service Layer

Orchestrates all LangGraph workflow executions:
1. `execute_travel_plan`: Starts a new travel request thread or continues an existing one.
2. `resume_travel_plan`: Resumes a thread paused for Human-in-the-Loop (HITL) approval with TTL and idempotency.
3. `stream_travel_events`: Generates Server-Sent Events (SSE) with graph updates, disconnect handling, and heartbeats.
4. Maintains run history in memory for observability, metrics, and workflow replay APIs.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import HTTPException, Request, status
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from tripmate.api.dependencies import validate_thread_ownership
from tripmate.config.settings import settings
from tripmate.core.singleton import SingletonMeta
from tripmate.database.store import store
from tripmate.graph.state import TravelState
from tripmate.graph.workflow import travel_workflow_graph
from tripmate.core.logging import get_structured_logger
from tripmate.services.observability import calculate_cost, estimate_tokens

logger = get_structured_logger("tripmate.travel_service")


class RunStoreProxy:
    """
    Persistent Workflow Run store proxy bridging workflow_run_repository
    (PostgreSQL workflow_runs table) with hybrid Redis caching and in-memory fallback.
    Maintains full dict-like interface compatibility.
    """

    def __init__(self):
        self._memory_cache: Dict[str, Dict[str, Any]] = {}

    def __getitem__(self, run_id: str) -> Dict[str, Any]:
        item = self.get(run_id)
        if item is None:
            raise KeyError(run_id)
        return item

    def __setitem__(self, run_id: str, payload: Dict[str, Any]) -> None:
        self._memory_cache[run_id] = payload
        try:
            from tripmate.repositories.store_repositories import workflow_run_repository

            workflow_run_repository.create(
                run_id=run_id,
                user_id=payload.get("user_id"),
                thread_id=payload.get("thread_id"),
                status=payload.get("status", "RUNNING"),
                query=payload.get("query") or payload.get("user_query"),
                itinerary=payload.get("itinerary") or payload.get("answer"),
                metrics=payload.get("metrics"),
                events=payload.get("events"),
            )
        except Exception as exc:
            logger.debug(f"Persistence notice for workflow run {run_id}: {exc}")

    def __contains__(self, run_id: object) -> bool:
        if not isinstance(run_id, str):
            return False
        return self.get(run_id) is not None

    def get(self, run_id: str, default: Any = None) -> Optional[Dict[str, Any]]:
        if run_id in self._memory_cache:
            return self._memory_cache[run_id]

        try:
            from tripmate.repositories.store_repositories import workflow_run_repository

            repo_run = workflow_run_repository.get_by_id(run_id)
            if repo_run:
                run_dict = dict(repo_run)
                if "answer" not in run_dict and "itinerary" in run_dict:
                    run_dict["answer"] = run_dict["itinerary"]
                self._memory_cache[run_id] = run_dict
                return run_dict
        except Exception as exc:
            logger.debug(f"Lookup notice for workflow run {run_id}: {exc}")

        return default

    def pop(self, run_id: str, default: Any = None) -> Any:
        return self._memory_cache.pop(run_id, default)

    def values(self) -> List[Dict[str, Any]]:
        try:
            from tripmate.repositories.store_repositories import workflow_run_repository

            repo_runs = workflow_run_repository.list_all(limit=100)
            seen_ids = set()
            combined = []
            for r in repo_runs:
                seen_ids.add(r["id"])
                combined.append(r)
            for k, v in self._memory_cache.items():
                if k not in seen_ids:
                    combined.append(v)
            return combined
        except Exception:
            return list(self._memory_cache.values())

    def keys(self) -> List[str]:
        return [r["id"] if "id" in r else r.get("run_id", "") for r in self.values()]

    def items(self) -> List[tuple[str, Dict[str, Any]]]:
        return [(k, self.get(k)) for k in self.keys() if self.get(k) is not None]

    def __iter__(self):
        return iter(self.keys())

    def __len__(self) -> int:
        return len(self.values())

    def clear(self) -> None:
        self._memory_cache.clear()


# Persistent store for workflow run telemetry and replay history
RUN_STORE: RunStoreProxy = RunStoreProxy()

# Active in-flight runs registry for graceful shutdown
ACTIVE_RUNS: set[asyncio.Task] = set()


def build_initial_travel_state(
    user_query: str,
    thread_id: Optional[str] = None,
    user_id: Optional[str] = None,
    run_id: Optional[str] = None,
    trip_constraints: Optional[Dict[str, Any]] = None,
    start_time: Optional[float] = None,
) -> TravelState:
    """Constructs a validated initial LangGraph TravelState dictionary."""
    cleaned_query = (user_query or "").strip()
    if not cleaned_query:
        raise ValueError("Cannot build TravelState: user_query must be provided.")

    effective_thread_id = (thread_id.strip() if thread_id and thread_id.strip() else None) or f"user_{uuid.uuid4().hex}"
    effective_run_id = (run_id.strip() if run_id and run_id.strip() else None) or f"run_{uuid.uuid4().hex[:12]}"

    return {
        "messages": [HumanMessage(content=cleaned_query)],
        "user_query": cleaned_query,
        "user_id": user_id.strip() if user_id and user_id.strip() else None,
        "thread_id": effective_thread_id,
        "run_id": effective_run_id,
        "status": "RUNNING",
        "guardrail_allowed": True,
        "guardrail_reason": "",
        "selected_agents": [],
        "trip_constraints": dict(trip_constraints) if trip_constraints else {},
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
        "start_time": start_time or time.time(),
        "metrics": {"agent_latencies": {}, "total_latency_ms": 0.0},
    }


def serialize_graph_result(result: Dict[str, Any], thread_id: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    """Formats internal graph dictionary into clean API response payload with telemetry."""
    interrupts = result.get("__interrupt__", [])
    interrupt_data = None
    if interrupts:
        first = interrupts[0]
        payload = getattr(first, "value", first)
        interrupt_data = payload if isinstance(payload, dict) else {"value": payload}

    messages = result.get("messages", [])
    last_message = messages[-1].content if messages else ""
    answer = result.get("final_response") or last_message

    if interrupt_data:
        answer = interrupt_data.get("draft_itinerary") or result.get("itinerary", "")

    effective_run_id = run_id or result.get("run_id") or f"run_{uuid.uuid4().hex[:12]}"

    raw_metrics = result.get("metrics", {})
    if isinstance(raw_metrics, dict):
        query_text = result.get("user_query", "")
        answer_text = str(answer)
        input_tokens = estimate_tokens(query_text)
        output_tokens = estimate_tokens(answer_text)
        cost_usd = calculate_cost("llama-3.3-70b-versatile", input_tokens, output_tokens)

        raw_metrics["token_usage"] = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
        raw_metrics["estimated_cost_usd"] = cost_usd

    payload = {
        "run_id": effective_run_id,
        "thread_id": thread_id,
        "user_id": result.get("user_id"),
        "status": result.get("status", "COMPLETED" if not interrupt_data else "WAITING_FOR_APPROVAL"),
        "answer": answer,
        "requires_approval": interrupt_data is not None,
        "approval_request": (
            interrupt_data.get("approval_request", "") if interrupt_data else result.get("approval_request", "")
        ),
        "flight_results": result.get("flight_results", ""),
        "hotel_results": result.get("hotel_results", ""),
        "weather_results": result.get("weather_results", ""),
        "budget_results": result.get("budget_results", ""),
        "itinerary": (interrupt_data.get("draft_itinerary", "") if interrupt_data else result.get("itinerary", "")),
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
        "metrics": raw_metrics,
    }

    RUN_STORE[effective_run_id] = payload
    return payload


class TravelService(metaclass=SingletonMeta):
    """Main service providing clean API interfaces for workflow invocation."""

    def __init__(self, data_store=None):
        self._store = data_store or store
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
            registered_owner = self._store.get_thread_owner(thread_id)
            if registered_owner and registered_owner != user_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "code": "THREAD_NOT_FOUND",
                        "message": f"Thread '{thread_id}' not found.",
                    },
                )
            self._store.register_thread_owner(thread_id, user_id)

        run_id = f"run_{uuid.uuid4().hex[:12]}"
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": settings.LANGGRAPH_RECURSION_LIMIT,
        }
        t0 = time.time()

        initial_state = build_initial_travel_state(
            user_query=user_input,
            thread_id=thread_id,
            user_id=user_id,
            run_id=run_id,
            start_time=t0,
        )

        result = await travel_workflow_graph.ainvoke(initial_state, config=config)
        serialized = serialize_graph_result(result, thread_id, run_id=run_id)

        if serialized.get("requires_approval"):
            now_ts = time.time()
            self._approval_timestamps[thread_id] = now_ts
            try:
                from tripmate.cache.redis_cache import hybrid_cache

                await hybrid_cache.set("approval_ts", thread_id, now_ts, ttl=settings.APPROVAL_TTL_SECONDS)
            except Exception:
                pass

        return serialized

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
                detail={
                    "code": "THREAD_NOT_FOUND",
                    "message": f"Thread ID '{thread_id}' not found or has no execution history.",
                },
            )

        # Idempotency check 2: if thread has already finished approval and completed
        state_values = getattr(state, "values", {}) or {}
        if not getattr(state, "next", None) and state_values.get("status") in (
            "APPROVED",
            "REVISION_REQUESTED",
            "COMPLETED",
        ):
            serialized = serialize_graph_result(state_values, thread_id)
            self._approval_history[thread_id] = serialized
            return serialized

        # State check: a thread can only be resumed when currently interrupted at human_approval
        if not getattr(state, "next", None) or "human_approval" not in getattr(state, "next", ()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_WORKFLOW_STATE",
                    "message": f"Thread ID '{thread_id}' is not currently waiting for approval.",
                },
            )

        # TTL validation on pending approval
        created_at = self._approval_timestamps.get(thread_id) or state_values.get("approval_created_at")
        if not created_at:
            try:
                from tripmate.cache.redis_cache import hybrid_cache

                cached_ts = await hybrid_cache.get("approval_ts", thread_id)
                if cached_ts:
                    created_at = float(cached_ts)
            except Exception:
                pass

        if created_at and (time.time() - created_at > settings.APPROVAL_TTL_SECONDS):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail={
                    "code": "APPROVAL_EXPIRED",
                    "message": f"Approval request for thread '{thread_id}' has expired.",
                },
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
        self._approval_history[thread_id] = serialized
        self._approval_timestamps.pop(thread_id, None)
        try:
            from tripmate.cache.redis_cache import hybrid_cache

            await hybrid_cache.delete("approval_ts", thread_id)
            await hybrid_cache.set("approval_history", thread_id, serialized)
        except Exception:
            pass
        return serialized

    async def cancel_expired_approvals(self) -> int:
        """Scheduled job that cancels pending HITL approval threads past APPROVAL_TTL_SECONDS."""
        now = time.time()
        cancelled_count = 0
        from tripmate.core.audit import AuditEventType, audit_logger
        from tripmate.repositories.store_repositories import workflow_run_repository

        for run_id in list(RUN_STORE.keys()):
            run = RUN_STORE.get(run_id)
            if not run or run.get("status") != "WAITING_FOR_APPROVAL":
                continue

            thread_id = run.get("thread_id")
            created_at = self._approval_timestamps.get(thread_id) or run.get("start_time")
            if not created_at and run.get("created_at"):
                try:
                    from datetime import datetime

                    dt = datetime.fromisoformat(run["created_at"])
                    created_at = dt.timestamp()
                except Exception:
                    pass

            if created_at and (now - created_at > settings.APPROVAL_TTL_SECONDS):
                run["status"] = "EXPIRED"
                RUN_STORE[run_id] = run
                if thread_id:
                    self._approval_timestamps.pop(thread_id, None)
                    try:
                        from tripmate.cache.redis_cache import hybrid_cache

                        await hybrid_cache.delete("approval_ts", thread_id)
                    except Exception:
                        pass
                try:
                    workflow_run_repository.update(run_id, {"status": "EXPIRED"})
                except Exception:
                    pass
                cancelled_count += 1

                audit_logger.record(
                    event_type=AuditEventType.APPROVAL_DECISION,
                    action="hitl_approval_expired",
                    actor="system_scheduler",
                    target_id=thread_id or run_id,
                    status="expired",
                    details={"run_id": run_id, "ttl_seconds": settings.APPROVAL_TTL_SECONDS},
                )
                logger.info(f"Marked pending approval thread '{thread_id}' (run {run_id}) as EXPIRED past TTL.")

        return cancelled_count

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
            yield ": heartbeat\n\n"
            yield f"event: workflow.started\ndata: {json.dumps({'thread_id': thread_id, 'request_id': request_id, 'status': 'started'})}\n\n"

            if user_id:
                registered_owner = await asyncio.to_thread(self._store.get_thread_owner, thread_id)
                if registered_owner and registered_owner != user_id:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "code": "THREAD_NOT_FOUND",
                            "message": f"Thread '{thread_id}' not found.",
                        },
                    )
                await asyncio.to_thread(self._store.register_thread_owner, thread_id, user_id)

            run_id = f"run_{uuid.uuid4().hex[:12]}"
            config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": settings.LANGGRAPH_RECURSION_LIMIT,
            }
            t0 = time.time()

            initial_input = build_initial_travel_state(
                user_query=user_input,
                thread_id=thread_id,
                user_id=user_id,
                run_id=run_id,
                start_time=t0,
            )

            # Stream real-time LangGraph execution progress using astream_events v2
            async for event in travel_workflow_graph.astream_events(initial_input, config=config, version="v2"):
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
                    if ev_name in (
                        "supervisor",
                        "parallel_specialists",
                        "critic",
                        "itinerary_agent",
                        "human_approval",
                        "final_agent",
                        "guardrail_blocked",
                    ):
                        yield f"event: step.update\ndata: {json.dumps({'step': ev_name, 'status': 'started'})}\n\n"
                        if ev_name == "parallel_specialists":
                            yield f"event: specialists.started\ndata: {json.dumps({'status': 'running'})}\n\n"

                # 3. Node / step completions & decisions
                elif ev_type == "on_chain_end":
                    if ev_name in (
                        "supervisor",
                        "parallel_specialists",
                        "critic",
                        "itinerary_agent",
                        "human_approval",
                        "final_agent",
                        "guardrail_blocked",
                    ):
                        yield f"event: step.update\ndata: {json.dumps({'step': ev_name, 'status': 'completed'})}\n\n"
                        output_data = data.get("output")
                        if ev_name == "supervisor" and isinstance(output_data, dict):
                            selected = output_data.get("selected_agents", [])
                            reasoning = output_data.get("supervisor_reasoning", "")
                            yield f"event: supervisor.decision\ndata: {json.dumps({'selected_agents': selected, 'reasoning': reasoning})}\n\n"
                            yield f"event: supervisor.completed\ndata: {json.dumps({'selected_agents': selected, 'reasoning': reasoning})}\n\n"
                        elif ev_name == "parallel_specialists":
                            yield f"event: specialists.completed\ndata: {json.dumps({'status': 'completed', 'node': ev_name})}\n\n"
                        elif ev_name == "critic" and isinstance(output_data, dict):
                            report = output_data.get("critic_report")
                            yield f"event: critic.completed\ndata: {json.dumps({'critic_report': report})}\n\n"
                        elif ev_name == "itinerary_agent":
                            yield f"event: itinerary.completed\ndata: {json.dumps({'status': 'draft_synthesized'})}\n\n"

                # 4. Token streaming deltas
                elif ev_type == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        yield f"event: token\ndata: {json.dumps({'content': chunk.content})}\n\n"

            if request and await request.is_disconnected():
                return

            state = await travel_workflow_graph.aget_state(config)
            state_values = getattr(state, "values", {}) or {}
            serialized = serialize_graph_result(state_values, thread_id, run_id=run_id)

            is_hitl = (
                serialized.get("requires_approval")
                or "human_approval" in getattr(state, "next", ())
                or state_values.get("status") == "WAITING_FOR_APPROVAL"
            )

            if is_hitl:
                self._approval_timestamps[thread_id] = time.time()
                yield f"event: hitl_required\ndata: {json.dumps({'approval_request': serialized.get('approval_request')})}\n\n"
                yield f"event: approval.required\ndata: {json.dumps({'approval_request': serialized.get('approval_request')})}\n\n"

            yield f"event: final_result\ndata: {json.dumps({'answer': serialized.get('answer'), 'itinerary': serialized.get('itinerary')})}\n\n"
            yield f"event: workflow.completed\ndata: {json.dumps({'success': True, 'request_id': request_id, **serialized})}\n\n"

        except asyncio.CancelledError:
            logger.info(f"Stream cancelled for thread '{thread_id}'.")
            return
        except Exception as exc:
            generic_err = f"Workflow error: {exc}"
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


# Shared singleton instance
travel_service = TravelService()
