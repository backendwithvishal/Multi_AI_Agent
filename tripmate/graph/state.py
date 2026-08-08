"""
LangGraph Shared Workflow State Schema

This module defines 'TravelState', the central data dictionary passed between all nodes in the LangGraph workflow.
It stores query inputs, plan DAGs, selected agents, specialist outputs, evidence items, critic reports, HITL approval status, and performance/token telemetry.
"""

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict
from langchain_core.messages import AnyMessage


class TravelState(TypedDict, total=False):
    # Message log history for chat memory
    messages: Annotated[List[AnyMessage], operator.add]
    
    # User input details & correlation keys
    user_query: str
    user_id: Optional[str]
    thread_id: str
    run_id: str

    # Workflow progress status (RUNNING, BLOCKED, WAITING_FOR_APPROVAL, COMPLETED, FAILED)
    status: str

    # Guardrail safety check outputs
    guardrail_allowed: bool
    guardrail_reason: str
    
    # Planner & Supervisor routing decisions & DAG task graph
    plan_dag: Dict[str, Any]
    selected_agents: List[str]
    trip_constraints: Dict[str, Any]
    supervisor_reasoning: str

    # Structured Specialist agent results & Evidence collection
    flight_results: str
    hotel_results: str
    weather_results: str
    budget_results: str
    itinerary: str
    structured_outputs: Dict[str, Any]
    evidence_items: List[Dict[str, Any]]

    # Critic & Validation report
    critic_report: Dict[str, Any]
    retry_count: int

    # Human-In-The-Loop (HITL) review & feedback
    approval_request: str
    approved: bool
    human_feedback: str
    final_response: str

    # Telemetry, token accounting & execution metrics
    llm_calls: int
    token_usage: Dict[str, Any]
    estimated_cost: float
    start_time: float
    metrics: Dict[str, Any]
