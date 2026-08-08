"""
Supervisor Agent Module

The Supervisor Agent orchestrates dynamic plan creation and agent routing:
1. Parses user input and extracts trip constraints.
2. Interacts with the DynamicPlanner to construct Task DAGs.
3. Consults the AgentRegistry to determine available agent capabilities.
"""

from typing import List, Any
from pydantic import BaseModel, Field

from tripmate.agents.planner import planner
from tripmate.agents.registry import agent_registry

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
    """Pydantic model representing extracted travel parameters."""
    destination: str = Field(default="")
    origin: str = Field(default="")
    duration: str = Field(default="")
    budget: str = Field(default="")
    travel_style: str = Field(default="")
    special_preferences: List[str] = Field(default_factory=list)


class SupervisorRouting(BaseModel):
    """Structured output containing selected agents and trip constraints."""
    selected_agents: List[str] = Field(default_factory=list)
    trip_constraints: TripConstraints = Field(default_factory=TripConstraints)
    reasoning: str = Field(default="")


async def run_supervisor_routing(llm: Any, user_query: str) -> SupervisorRouting:
    """Uses LLM reasoning & DynamicPlanner to extract constraints and route work."""
    try:
        plan_dag = await planner.create_plan(llm, user_query)
        selected_set = {task.agent for task in plan_dag.tasks}

        validated_agents = [
            agent for agent in AGENT_ORDER
            if agent in selected_set or agent in KNOWN_AGENTS
        ]
        if "itinerary_agent" not in validated_agents:
            validated_agents.append("itinerary_agent")

        raw_constraints = plan_dag.trip_constraints
        constraints = TripConstraints(
            destination=raw_constraints.get("destination", ""),
            origin=raw_constraints.get("origin", ""),
            duration=raw_constraints.get("duration", ""),
            budget=raw_constraints.get("budget", ""),
            travel_style=raw_constraints.get("travel_style", ""),
            special_preferences=raw_constraints.get("special_preferences", []),
        )

        return SupervisorRouting(
            selected_agents=validated_agents,
            trip_constraints=constraints,
            reasoning=plan_dag.reasoning or "Dynamic DAG plan selected.",
        )
    except Exception as exc:
        print(f"Supervisor routing fallback: {exc}")

    return SupervisorRouting(
        selected_agents=AGENT_ORDER.copy(),
        reasoning="Fallback routing selected full default workflow.",
    )
