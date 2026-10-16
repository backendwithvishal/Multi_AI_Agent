"""
Travel Workflow State Builder Pattern

Provides validated, step-by-step construction of the multi-attribute TravelState dictionary
consumed by the LangGraph execution graph. Eliminates duplicated dictionary literals and
guarantees all mandatory keys and default states are consistently initialized.
"""

import time
import uuid
from typing import Any, Dict, List, Optional
from langchain_core.messages import HumanMessage, BaseMessage
from tripmate.graph.state import TravelState


class TravelWorkflowStateBuilder:
    """
    Builder pattern for constructing validated LangGraph TravelState dictionaries.
    """

    def __init__(self):
        self._user_query: str = ""
        self._thread_id: Optional[str] = None
        self._user_id: Optional[str] = None
        self._run_id: Optional[str] = None
        self._trip_constraints: Dict[str, Any] = {}
        self._initial_messages: List[BaseMessage] = []
        self._start_time: float = time.time()
        self._metrics: Dict[str, Any] = {"agent_latencies": {}, "total_latency_ms": 0.0}

    def with_user_query(self, query: str) -> "TravelWorkflowStateBuilder":
        """Sets user query prompt and validates non-emptiness."""
        cleaned = (query or "").strip()
        if not cleaned:
            raise ValueError("user_query cannot be empty.")
        self._user_query = cleaned
        if not self._initial_messages:
            self._initial_messages = [HumanMessage(content=cleaned)]
        return self

    def with_thread_id(self, thread_id: Optional[str]) -> "TravelWorkflowStateBuilder":
        """Sets conversation thread ID, generating a unique ID if none provided."""
        self._thread_id = thread_id.strip() if thread_id and thread_id.strip() else None
        return self

    def with_user_id(self, user_id: Optional[str]) -> "TravelWorkflowStateBuilder":
        """Sets optional authenticated user ID."""
        self._user_id = user_id.strip() if user_id and user_id.strip() else None
        return self

    def with_run_id(self, run_id: Optional[str]) -> "TravelWorkflowStateBuilder":
        """Sets execution run ID."""
        self._run_id = run_id.strip() if run_id and run_id.strip() else None
        return self

    def with_constraints(self, constraints: Dict[str, Any]) -> "TravelWorkflowStateBuilder":
        """Sets preliminary trip constraints."""
        self._trip_constraints = dict(constraints) if constraints else {}
        return self

    def with_start_time(self, t0: float) -> "TravelWorkflowStateBuilder":
        """Sets initial invocation timestamp."""
        self._start_time = t0
        return self

    def build(self) -> TravelState:
        """
        Validates required fields and returns a fully initialized TravelState dictionary.
        """
        if not self._user_query:
            raise ValueError("Cannot build TravelState: user_query must be provided.")

        effective_thread_id = self._thread_id or f"user_{uuid.uuid4().hex}"
        effective_run_id = self._run_id or f"run_{uuid.uuid4().hex[:12]}"

        state: TravelState = {
            "messages": self._initial_messages,
            "user_query": self._user_query,
            "user_id": self._user_id,
            "thread_id": effective_thread_id,
            "run_id": effective_run_id,
            "status": "RUNNING",
            "guardrail_allowed": True,
            "guardrail_reason": "",
            "selected_agents": [],
            "trip_constraints": self._trip_constraints,
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
            "start_time": self._start_time,
            "metrics": self._metrics,
        }
        return state
