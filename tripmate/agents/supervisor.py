import json
from typing import List
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

KNOWN_AGENTS = {
    "flight_agent",
    "hotel_agent",
    "weather_agent",
    "budget_agent",
    "itinerary_agent",
}

AGENT_ORDER = [
    "flight_agent",
    "hotel_agent",
    "weather_agent",
    "budget_agent",
    "itinerary_agent",
]


class TripConstraints(BaseModel):
    destination: str = Field(default="")
    origin: str = Field(default="")
    duration: str = Field(default="")
    budget: str = Field(default="")
    travel_style: str = Field(default="")
    special_preferences: List[str] = Field(default_factory=list)


class SupervisorRouting(BaseModel):
    selected_agents: List[str] = Field(default_factory=list)
    trip_constraints: TripConstraints = Field(default_factory=TripConstraints)
    reasoning: str = Field(default="")


async def run_supervisor_routing(llm, user_query: str) -> SupervisorRouting:
    if not llm:
        return SupervisorRouting(
            selected_agents=AGENT_ORDER.copy(),
            reasoning="Default full workflow selected (LLM key unconfigured)"
        )

    prompt = f"""
You are the supervisor of a multi-agent travel-planning system.
Select the specialist agents needed for the request.

Available agents:
- flight_agent: flights, airports, airlines, routes
- hotel_agent: hotels, accommodation, places to stay
- weather_agent: weather, climate, season, packing advice
- budget_agent: cost, price limits, budget feasibility
- itinerary_agent: creates integrated plan (always included)

Return strict JSON matching this schema:
{{
  "selected_agents": ["flight_agent", "hotel_agent", "weather_agent", "budget_agent", "itinerary_agent"],
  "trip_constraints": {{
    "destination": "",
    "origin": "",
    "duration": "",
    "budget": "",
    "travel_style": "",
    "special_preferences": []
  }},
  "reasoning": ""
}}

User request: {user_query}
"""

    try:
        response = await llm.ainvoke(
            [
                SystemMessage(content="You route work to travel specialist agents. Return strict JSON only."),
                HumanMessage(content=prompt),
            ]
        )
        cleaned = str(response.content).strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[-1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            data = json.loads(cleaned[start:end+1])
            routing = SupervisorRouting(**data)
            
            validated_agents = [
                agent for agent in AGENT_ORDER
                if agent in routing.selected_agents and agent in KNOWN_AGENTS
            ]
            if "itinerary_agent" not in validated_agents:
                validated_agents.append("itinerary_agent")

            routing.selected_agents = validated_agents
            return routing
    except Exception as exc:
        print(f"Supervisor parsing fallback: {exc}")

    return SupervisorRouting(
        selected_agents=AGENT_ORDER.copy(),
        reasoning="Fallback routing selected full workflow."
    )
