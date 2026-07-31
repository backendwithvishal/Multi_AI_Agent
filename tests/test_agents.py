# pyrefly: ignore [missing-import]
import pytest
from unittest.mock import AsyncMock, patch

from backend import (
    _json_from_llm,
    _empty_constraints,
    supervisor_agent,
    guardrail_blocked_agent,
    TravelState,
)


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
@patch("backend._llm_text", new_callable=AsyncMock)
async def test_supervisor_agent_allowed(mock_llm_text):
    mock_llm_text.side_effect = [
        '{"allowed": true, "reason": ""}',
        '{"selected_agents": ["flight_agent", "hotel_agent"], "trip_constraints": {"destination": "Paris"}, "reasoning": "Valid Paris trip"}',
    ]

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
