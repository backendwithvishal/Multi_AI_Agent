"""
LangGraph Shared Workflow State Schema

This module defines 'TravelState', the central data dictionary passed between all agents in the LangGraph workflow.
It stores input query, guardrail status, chosen specialist agents, intermediate agent outputs, human approval decisions, and performance metrics.
"""

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict
from langchain_core.messages import AnyMessage


class TravelState(TypedDict, total=False):
    # Message log history for chat memory
    messages: Annotated[List[AnyMessage], operator.add]
    
    # User input details
    user_query: str
    user_id: Optional[str]
    thread_id: str

    # Workflow progress status (RUNNING, BLOCKED, WAITING_FOR_APPROVAL, COMPLETED)
    status: str

    # Guardrail safety check outputs
    guardrail_allowed: bool
    guardrail_reason: str
    
    # Supervisor routing decisions & trip constraints (destination, budget, duration)
    selected_agents: List[str]
    trip_constraints: Dict[str, Any]
    supervisor_reasoning: str

    # Specialist agent results
    flight_results: str
    hotel_results: str
    weather_results: str
    budget_results: str
    itinerary: str

    # Human-In-The-Loop (HITL) review & feedback
    approval_request: str
    approved: bool
    human_feedback: str
    final_response: str

    # System execution telemetry and latency measurements
    llm_calls: int
    start_time: float
    metrics: Dict[str, Any]
