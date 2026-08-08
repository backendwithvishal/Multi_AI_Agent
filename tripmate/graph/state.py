import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict
from langchain_core.messages import AnyMessage


class TravelState(TypedDict, total=False):
    messages: Annotated[List[AnyMessage], operator.add]
    user_query: str
    user_id: Optional[str]
    thread_id: str

    status: str

    guardrail_allowed: bool
    guardrail_reason: str
    selected_agents: List[str]
    trip_constraints: Dict[str, Any]
    supervisor_reasoning: str

    flight_results: str
    hotel_results: str
    weather_results: str
    budget_results: str
    itinerary: str

    approval_request: str
    approved: bool
    human_feedback: str
    final_response: str

    llm_calls: int
    start_time: float
    metrics: Dict[str, Any]
