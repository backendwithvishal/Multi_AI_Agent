"""
Travel Plan Response Builder Pattern

Builds and serializes structured travel plan execution response payloads,
including token usage estimates, cost accounting, Human-in-the-Loop interrupts,
and telemetry.
"""

import uuid
from typing import Any, Dict, Optional
from tripmate.services.observability import estimate_tokens, calculate_cost


class TravelPlanResponseBuilder:
    """
    Builder pattern for constructing standardized workflow result dictionaries.
    """

    def __init__(self, raw_result: Dict[str, Any], thread_id: str):
        self._raw_result = raw_result
        self._thread_id = thread_id
        self._run_id: Optional[str] = None
        self._model_name: str = "llama-3.3-70b-versatile"

    def with_run_id(self, run_id: Optional[str]) -> "TravelPlanResponseBuilder":
        self._run_id = run_id
        return self

    def with_model_name(self, model_name: str) -> "TravelPlanResponseBuilder":
        self._model_name = model_name
        return self

    def _extract_interrupt(self) -> Optional[Dict[str, Any]]:
        interrupts = self._raw_result.get("__interrupt__", [])
        if not interrupts:
            return None
        first = interrupts[0]
        payload = getattr(first, "value", first)
        return payload if isinstance(payload, dict) else {"value": payload}

    def build(self) -> Dict[str, Any]:
        """Constructs and returns serialized response payload."""
        messages = self._raw_result.get("messages", [])
        last_message = messages[-1].content if messages else ""
        answer = self._raw_result.get("final_response") or last_message
        interrupt_data = self._extract_interrupt()

        if interrupt_data:
            answer = interrupt_data.get("draft_itinerary") or self._raw_result.get("itinerary", "")

        effective_run_id = (
            self._run_id
            or self._raw_result.get("run_id")
            or f"run_{uuid.uuid4().hex[:12]}"
        )

        raw_metrics = self._raw_result.get("metrics", {})
        if isinstance(raw_metrics, dict):
            query_text = self._raw_result.get("user_query", "")
            answer_text = str(answer)
            input_tokens = estimate_tokens(query_text)
            output_tokens = estimate_tokens(answer_text)
            cost_usd = calculate_cost(self._model_name, input_tokens, output_tokens)

            raw_metrics["token_usage"] = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            }
            raw_metrics["estimated_cost_usd"] = cost_usd

        return {
            "run_id": effective_run_id,
            "thread_id": self._thread_id,
            "status": self._raw_result.get(
                "status", "COMPLETED" if not interrupt_data else "WAITING_FOR_APPROVAL"
            ),
            "answer": answer,
            "requires_approval": interrupt_data is not None,
            "approval_request": (
                interrupt_data.get("approval_request", "")
                if interrupt_data
                else self._raw_result.get("approval_request", "")
            ),
            "flight_results": self._raw_result.get("flight_results", ""),
            "hotel_results": self._raw_result.get("hotel_results", ""),
            "weather_results": self._raw_result.get("weather_results", ""),
            "budget_results": self._raw_result.get("budget_results", ""),
            "itinerary": (
                interrupt_data.get("draft_itinerary", "")
                if interrupt_data
                else self._raw_result.get("itinerary", "")
            ),
            "selected_agents": self._raw_result.get("selected_agents", []),
            "trip_constraints": self._raw_result.get("trip_constraints", {}),
            "supervisor_reasoning": self._raw_result.get("supervisor_reasoning", ""),
            "guardrail_allowed": self._raw_result.get("guardrail_allowed", True),
            "guardrail_reason": self._raw_result.get("guardrail_reason", ""),
            "critic_report": self._raw_result.get("critic_report"),
            "evidence_items": self._raw_result.get("evidence_items", []),
            "structured_outputs": self._raw_result.get("structured_outputs", {}),
            "approved": self._raw_result.get("approved"),
            "human_feedback": self._raw_result.get("human_feedback", ""),
            "llm_calls": self._raw_result.get("llm_calls", 0),
            "metrics": raw_metrics,
        }
