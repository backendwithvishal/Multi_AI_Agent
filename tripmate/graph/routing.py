from tripmate.graph.state import TravelState

ROUTE_MAP = {
    "guardrail_blocked": "guardrail_blocked",
    "parallel_specialists": "parallel_specialists",
    "itinerary_agent": "itinerary_agent",
}


def route_from_supervisor(state: TravelState) -> str:
    if not state.get("guardrail_allowed", True):
        return "guardrail_blocked"
    return "parallel_specialists"
