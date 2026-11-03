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


@pytest.mark.asyncio
@patch("tripmate.graph.workflow.run_guardrail_check", new_callable=AsyncMock)
async def test_supervisor_agent_blocked(mock_guardrail):
    mock_guardrail.return_value = (False, "Request blocked due to dangerous keywords.")

    state: TravelState = {
        "user_query": "illegal instructions",
        "messages": [],
    }

    res = await supervisor_agent(state)
    assert res["status"] == "BLOCKED"
    assert res["guardrail_allowed"] is False
    assert res["guardrail_reason"] == "Request blocked due to dangerous keywords."
    assert res["selected_agents"] == []


@pytest.mark.asyncio
async def test_critic_node():
    from tripmate.graph.workflow import critic_node
    from tripmate.schemas.agents import CriticReport

    state: TravelState = {
        "user_query": "Trip to Paris",
        "trip_constraints": {"destination": "Paris"},
        "flight_results": "Flight found",
        "hotel_results": "Hotel found",
        "metrics": {"agent_latencies": {}},
    }

    mock_report = CriticReport(
        is_valid=True,
        score=0.95,
        violations=[],
        recommendations=["Plan satisfies all constraints."],
    )

    with patch("tripmate.agents.critic.critic_agent.evaluate_plan", new_callable=AsyncMock) as mock_eval:
        mock_eval.return_value = mock_report
        res = await critic_node(state)
        assert "critic_report" in res
        assert res["critic_report"]["is_valid"] is True
        assert res["critic_report"]["score"] == 0.95
        assert "critic_agent" in res["metrics"]["agent_latencies"]


@pytest.mark.asyncio
async def test_itinerary_node():
    from tripmate.graph.workflow import itinerary_node
    from tripmate.schemas.agents import StructuredAgentOutput

    state: TravelState = {
        "user_query": "3 days in Paris",
        "trip_constraints": {"destination": "Paris"},
        "flight_results": "Air France 100",
        "hotel_results": "Hotel Paris",
        "metrics": {"agent_latencies": {}},
    }

    mock_out = StructuredAgentOutput(
        agent_name="itinerary_agent",
        status="success",
        result="Day 1: Louvre. Day 2: Eiffel Tower. Day 3: Montmartre.",
    )

    with patch("tripmate.graph.workflow.itinerary_agent_obj.run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_out
        res = await itinerary_node(state)
        assert res["status"] == "WAITING_FOR_APPROVAL"
        assert "Day 1: Louvre" in res["itinerary"]
        assert "itinerary_agent" in res["metrics"]["agent_latencies"]


@pytest.mark.asyncio
async def test_human_approval_node_approved():
    from tripmate.graph.workflow import human_approval_node

    state: TravelState = {
        "itinerary": "Draft itinerary",
        "approval_request": "Please review",
    }

    with patch("tripmate.graph.workflow.interrupt") as mock_interrupt:
        mock_interrupt.return_value = {"approved": True, "feedback": "Looks great!"}
        res = await human_approval_node(state)
        assert res["status"] == "APPROVED"
        assert res["approved"] is True
        assert res["human_feedback"] == "Looks great!"


@pytest.mark.asyncio
async def test_human_approval_node_rejected():
    from tripmate.graph.workflow import human_approval_node

    state: TravelState = {
        "itinerary": "Draft itinerary",
        "approval_request": "Please review",
    }

    with patch("tripmate.graph.workflow.interrupt") as mock_interrupt:
        mock_interrupt.return_value = {"approved": False, "feedback": "Need cheaper hotels."}
        res = await human_approval_node(state)
        assert res["status"] == "REVISION_REQUESTED"
        assert res["approved"] is False
        assert res["human_feedback"] == "Need cheaper hotels."


@pytest.mark.asyncio
async def test_final_node():
    from tripmate.graph.workflow import final_node

    state: TravelState = {
        "user_query": "Trip to Paris",
        "itinerary": "Approved itinerary",
        "metrics": {"agent_latencies": {}},
    }

    with patch("tripmate.graph.workflow.run_final_agent", new_callable=AsyncMock) as mock_final:
        mock_final.return_value = "Your final travel itinerary for Paris is confirmed!"
        res = await final_node(state)
        assert res["status"] == "COMPLETED"
        assert "confirmed" in res["final_response"]
        assert "final_agent" in res["metrics"]["agent_latencies"]
