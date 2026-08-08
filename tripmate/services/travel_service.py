import json
import time
import uuid
from typing import Any, Dict, Optional, AsyncGenerator
from langchain_core.messages import HumanMessage
# pyrefly: ignore [missing-import]
from langgraph.types import Command

from tripmate.graph.workflow import travel_workflow_graph


def _interrupt_payload(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    interrupts = result.get("__interrupt__", [])
    if not interrupts:
        return None
    first = interrupts[0]
    payload = getattr(first, "value", first)
    return payload if isinstance(payload, dict) else {"value": payload}


def serialize_graph_result(result: Dict[str, Any], thread_id: str) -> Dict[str, Any]:
    messages = result.get("messages", [])
    last_message = messages[-1].content if messages else ""
    answer = result.get("final_response") or last_message
    interrupt_data = _interrupt_payload(result)

    if interrupt_data:
        answer = interrupt_data.get("draft_itinerary") or result.get("itinerary", "")

    return {
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
        "approved": result.get("approved"),
        "human_feedback": result.get("human_feedback", ""),
        "llm_calls": result.get("llm_calls", 0),
        "metrics": result.get("metrics", {}),
    }


class TravelService:
    async def execute_travel_plan(self, user_input: str, thread_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
        if not thread_id:
            thread_id = f"user_{uuid.uuid4().hex}"

        config = {"configurable": {"thread_id": thread_id}}
        t0 = time.time()

        result = await travel_workflow_graph.ainvoke(
            {
                "messages": [HumanMessage(content=user_input)],
                "user_query": user_input,
                "user_id": user_id,
                "thread_id": thread_id,
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
                "llm_calls": 0,
                "start_time": t0,
                "metrics": {"agent_latencies": {}, "total_latency_ms": 0.0},
            },
            config=config,
        )
        return serialize_graph_result(result, thread_id)

    async def resume_travel_plan(self, thread_id: str, approved: bool, feedback: str = "") -> Dict[str, Any]:
        config = {"configurable": {"thread_id": thread_id}}
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

    async def stream_travel_events(self, user_input: str, thread_id: str, request_id: str) -> AsyncGenerator[str, None]:
        yield f"event: workflow.started\ndata: {json.dumps({'thread_id': thread_id, 'request_id': request_id, 'status': 'started'})}\n\n"
        
        try:
            result = await self.execute_travel_plan(user_input, thread_id)
            selected = result.get("selected_agents", [])
            yield f"event: supervisor.completed\ndata: {json.dumps({'selected_agents': selected, 'reasoning': result.get('supervisor_reasoning')})}\n\n"

            for agent in selected:
                yield f"event: agent.completed\ndata: {json.dumps({'agent': agent, 'status': 'completed'})}\n\n"

            if result.get("requires_approval"):
                yield f"event: approval.required\ndata: {json.dumps({'approval_request': result.get('approval_request')})}\n\n"

            yield f"event: workflow.completed\ndata: {json.dumps({'success': True, 'request_id': request_id, **result})}\n\n"
        except Exception as exc:
            yield f"event: workflow.failed\ndata: {json.dumps({'success': False, 'error': str(exc), 'request_id': request_id})}\n\n"


travel_service = TravelService()
