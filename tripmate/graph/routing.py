"""
Supervisor Graph Routing Logic

This module decides where the workflow should go after the Supervisor node finishes:
1. If the Guardrail check blocked the user's request, route to 'guardrail_blocked'.
2. Otherwise, route to 'parallel_specialists' to run flight, hotel, and weather agents in parallel.
"""

from tripmate.graph.state import TravelState

# Maps routing decision string to next target node name in LangGraph workflow
ROUTE_MAP = {
    "guardrail_blocked": "guardrail_blocked",
    "parallel_specialists": "parallel_specialists",
    "itinerary_agent": "itinerary_agent",
}


def route_from_supervisor(state: TravelState) -> str:
    """
    Decides the next node after the supervisor step based on guardrail output.
    """
    if not state.get("guardrail_allowed", True):
        # Stop workflow early if safety guardrail rejected the request
        return "guardrail_blocked"
    
    # Send request to parallel specialist agents (Flight, Hotel, Weather)
    return "parallel_specialists"
