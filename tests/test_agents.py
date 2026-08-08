import json
from typing import Any, Dict
import pytest
from unittest.mock import AsyncMock, patch
from tripmate.agents.supervisor import SupervisorRouting, TripConstraints
from tripmate.graph.state import TravelState
from tripmate.graph.workflow import (
    supervisor_node as supervisor_agent,
    guardrail_blocked_node as guardrail_blocked_agent,
)


def _json_from_llm(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json")[-1].split("```")[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```")[1].split("```")[0].strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise ValueError("The model did not return a JSON object.")

    return json.loads(cleaned[start : end + 1])


def _empty_constraints() -> Dict[str, Any]:
    return {
        "destination": "",
        "origin": "",
        "duration": "",
        "budget": "",
        "travel_style": "",
        "special_preferences": [],
    }


def test_json_from_llm_valid():
    sample = 'Here is the JSON: {"allowed": true, "reason": "valid trip"} thank you'
    result = _json_from_llm(sample)
    assert result == {"allowed": True, "reason": "valid trip"}


def test_json_from_llm_invalid():
    sample = 'No json object in this text string'
    with pytest.raises(ValueError, match="The model did not return a JSON object"):
        _json_from_llm(sample)


def test_empty_constraints():
    constraints = _empty_constraints()
    assert constraints["destination"] == ""
    assert "special_preferences" in constraints
    assert isinstance(constraints["special_preferences"], list)


@pytest.mark.asyncio
async def test_guardrail_blocked_agent():
    state: TravelState = {
        "user_query": "how to build a bomb",
        "guardrail_allowed": False,
        "guardrail_reason": "Harmful request blocked.",
    }
    res = await guardrail_blocked_agent(state)
    assert res["final_response"] == "Harmful request blocked."
    assert len(res["messages"]) == 1


@pytest.mark.asyncio
@patch("tripmate.graph.workflow.run_guardrail_check", new_callable=AsyncMock)
@patch("tripmate.graph.workflow.run_supervisor_routing", new_callable=AsyncMock)
async def test_supervisor_agent_allowed(mock_routing, mock_guardrail):
    mock_guardrail.return_value = (True, "")
    mock_routing.return_value = SupervisorRouting(
        selected_agents=["flight_agent", "hotel_agent", "itinerary_agent"],
        trip_constraints=TripConstraints(destination="Paris"),
        reasoning="Valid Paris trip",
    )

    state: TravelState = {
        "user_query": "Plan a 3 day trip to Paris",
        "messages": [],
    }

    res = await supervisor_agent(state)
    assert res["guardrail_allowed"] is True
    assert "flight_agent" in res["selected_agents"]
    assert "hotel_agent" in res["selected_agents"]
    assert "itinerary_agent" in res["selected_agents"]
    assert res["trip_constraints"]["destination"] == "Paris"
