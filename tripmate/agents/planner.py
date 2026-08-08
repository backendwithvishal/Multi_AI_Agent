"""
Dynamic Task Planner Module

This module decomposes complex user requests into structured Task DAGs (Directed Acyclic Graphs).
Determines:
- Task dependencies (`depends_on`)
- Priority and risk levels
- Agent assignments from the AgentRegistry
- Fallback execution paths
"""

import json
from typing import Any, Dict, List
from langchain_core.messages import SystemMessage, HumanMessage

from tripmate.schemas.agents import TaskSpec, PlanDAG
from tripmate.agents.registry import agent_registry


class DynamicPlanner:
    """Decomposes goals into dependency-aware Task DAGs."""

    async def create_plan(self, llm: Any, user_query: str) -> PlanDAG:
        """Decomposes a user request into a PlanDAG."""
        if not llm:
            return self._default_plan(user_query, "LLM unconfigured fallback")

        registered_agents = agent_registry.list_agents()
        agent_descriptions = "\n".join(
            f"- {a.name}: {a.description} (capabilities: {', '.join(a.capabilities)})"
            for a in registered_agents
        ) or (
            "- flight_agent: flight status, airlines, options\n"
            "- hotel_agent: hotel accommodations\n"
            "- weather_agent: current weather & forecasts\n"
            "- budget_agent: cost calculations & budget advice\n"
            "- itinerary_agent: day-by-day draft itinerary"
        )

        prompt = f"""
You are the lead AI planner for an autonomous multi-agent system.
Decompose the following request into a structured task graph (DAG).

Available Registered Agents:
{agent_descriptions}

Rules:
1. Break down the user request into logical tasks.
2. For each task, specify:
   - task_id: unique slug (e.g. flight_search, hotel_search)
   - agent: registered agent name
   - depends_on: list of task_ids that must finish before this task runs
   - priority: low, medium, or high
   - retry_limit: number of retries (1-3)
   - risk_level: low, medium, or high
3. Tasks with no dependencies run in parallel.
4. Always include an itinerary synthesis step depending on specialist outputs.

Return strict JSON matching this schema:
{{
  "tasks": [
    {{
      "task_id": "flight_search",
      "agent": "flight_agent",
      "depends_on": [],
      "priority": "high",
      "retry_limit": 2,
      "risk_level": "low"
    }},
    ...
  ],
  "trip_constraints": {{
    "destination": "",
    "origin": "",
    "duration": "",
    "budget": ""
  }},
  "reasoning": "Brief explanation of plan structure"
}}

User Request: {user_query}
"""

        try:
            response = await llm.ainvoke(
                [
                    SystemMessage(content="You create structured multi-agent task execution plans. Return strict JSON only."),
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
                tasks = [TaskSpec(**t) for t in data.get("tasks", [])]
                if tasks:
                    return PlanDAG(
                        tasks=tasks,
                        reasoning=data.get("reasoning", "Dynamic plan generated."),
                        trip_constraints=data.get("trip_constraints", {}),
                    )
        except Exception as exc:
            print(f"Dynamic planner fallback: {exc}")

        return self._default_plan(user_query, "Fallback standard execution plan")

    def _default_plan(self, query: str, reasoning: str) -> PlanDAG:
        """Returns standard default DAG for travel planning requests."""
        tasks = [
            TaskSpec(task_id="flight_search", agent="flight_agent", depends_on=[], priority="high", retry_limit=2),
            TaskSpec(task_id="hotel_search", agent="hotel_agent", depends_on=[], priority="high", retry_limit=2),
            TaskSpec(task_id="weather_search", agent="weather_agent", depends_on=[], priority="medium", retry_limit=2),
            TaskSpec(task_id="budget_analysis", agent="budget_agent", depends_on=["flight_search", "hotel_search"], priority="medium", retry_limit=2),
            TaskSpec(task_id="itinerary_synthesis", agent="itinerary_agent", depends_on=["flight_search", "hotel_search", "weather_search", "budget_analysis"], priority="high", retry_limit=1),
        ]
        return PlanDAG(
            tasks=tasks,
            reasoning=reasoning,
            trip_constraints={"destination": "", "origin": "", "duration": "", "budget": ""},
        )


planner = DynamicPlanner()
