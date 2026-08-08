import asyncio
import json
import operator
import os
import time
import uuid
from typing import Annotated, Any, Dict, List, Optional, TypedDict

import certifi
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

# pyrefly: ignore [missing-import]
import psycopg
# pyrefly: ignore [missing-import]
from psycopg.rows import dict_row
# pyrefly: ignore [missing-import]
from langgraph.graph import StateGraph, START, END
# pyrefly: ignore [missing-import]
from langgraph.checkpoint.postgres import PostgresSaver
# pyrefly: ignore [missing-import]
from langgraph.types import Command, interrupt
# pyrefly: ignore [missing-import]
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
)
# pyrefly: ignore [missing-import]
from langchain_groq import ChatGroq

from backend_cache import mcp_cache
from mcp_client import (
    tavily_mcp_search,
    aviation_mcp_call,
    extract_destination,
    forecast_mcp_search,
    weather_mcp_search,
)


def get_database_url():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError(
            "DATABASE_URL is missing. Please add your PostgreSQL External Database URL to .env"
        )
    if "sslmode=" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"
    return database_url


GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

if GROQ_API_KEY:
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=GROQ_API_KEY,
    )
else:
    llm = None


# =========================================================
# Pydantic Schemas for Strict Output Validation
# =========================================================
class GuardrailDecision(BaseModel):
    allowed: bool = Field(description="Whether the travel request is safe and relevant")
    reason: str = Field(default="", description="Reason for blocking if disallowed")


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


# =========================================================
# State Schema
# =========================================================
class TravelState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str

    # Supervisor + guardrail state
    guardrail_allowed: bool
    guardrail_reason: str
    selected_agents: list[str]
    trip_constraints: dict[str, Any]
    supervisor_reasoning: str

    # Specialist agent results
    flight_results: str
    hotel_results: str
    weather_results: str
    budget_results: str
    itinerary: str

    # HITL state
    approval_request: str
    approved: bool
    human_feedback: str
    final_response: str

    # Performance & Telemetry metrics
    llm_calls: int
    start_time: float
    metrics: dict[str, Any]


# =========================================================
# Helpers
# =========================================================
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


async def _llm_text(system_prompt: str, user_prompt: str) -> str:
    if not llm:
        raise ValueError("GROQ_API_KEY is missing. Please add GROQ_API_KEY to .env file.")
    response = await llm.ainvoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )
    return str(response.content)


def _json_from_llm(text: str) -> dict[str, Any]:
    """Extract the first complete JSON object returned by the model."""
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


def _empty_constraints() -> dict[str, Any]:
    return {
        "destination": "",
        "origin": "",
        "duration": "",
        "budget": "",
        "travel_style": "",
        "special_preferences": [],
    }


def _update_agent_latency(metrics: dict, agent_name: str, latency_ms: float):
    agent_latencies = metrics.get("agent_latencies", {})
    agent_latencies[agent_name] = round(latency_ms, 2)
    metrics["agent_latencies"] = agent_latencies


# =========================================================
# Supervisor Agent + Input Guardrail Node
# =========================================================
async def supervisor_agent(state: TravelState):
    t0 = time.time()
    query = state["user_query"]
    llm_calls = state.get("llm_calls", 0)
    metrics = state.get("metrics", {"agent_latencies": {}, "total_latency_ms": 0.0})

    guardrail_prompt = f"""
Determine whether the following request belongs to travel planning or travel information.
Valid requests: destinations, flights, hotels, weather, budgets, visas, transportation, sightseeing, food, packing, itineraries.
Block unrelated, illegal, or harmful requests.

Return strict JSON matching this schema:
{{
  "allowed": true,
  "reason": ""
}}

User request: {query}
"""

    try:
        guardrail_raw = await _llm_text(
            "You are the input guardrail for a travel-planning application. Return strict JSON only.",
            guardrail_prompt,
        )
        guard_data = _json_from_llm(guardrail_raw)
        decision = GuardrailDecision(**guard_data)
        allowed = decision.allowed
        guardrail_reason = decision.reason.strip()
        llm_calls += 1
    except Exception as exc:
        print(f"Guardrail fallback used: {exc}")
        allowed = True
        guardrail_reason = "Guardrail validation fallback allowed the request."

    if not allowed:
        reason = guardrail_reason or "TripMate AI can only help with travel-planning requests."
        _update_agent_latency(metrics, "supervisor_guardrail", (time.time() - t0) * 1000)
        return {
            "guardrail_allowed": False,
            "guardrail_reason": reason,
            "selected_agents": [],
            "trip_constraints": _empty_constraints(),
            "supervisor_reasoning": reason,
            "final_response": reason,
            "messages": [AIMessage(content=f"Guardrail blocked request: {reason}")],
            "llm_calls": llm_calls,
            "metrics": metrics,
        }

    supervisor_prompt = f"""
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

User request: {query}
"""

    try:
        supervisor_raw = await _llm_text(
            "You route work to travel specialist agents. Return strict JSON only.",
            supervisor_prompt,
        )
        routing_data = _json_from_llm(supervisor_raw)
        routing = SupervisorRouting(**routing_data)
        
        selected_agents = [
            name for name in AGENT_ORDER
            if name in routing.selected_agents and name in KNOWN_AGENTS
        ]
        if "itinerary_agent" not in selected_agents:
            selected_agents.append("itinerary_agent")

        constraints = routing.trip_constraints.model_dump()
        reasoning = routing.reasoning.strip()
        llm_calls += 1
    except Exception as exc:
        print(f"Supervisor fallback used: {exc}")
        selected_agents = AGENT_ORDER.copy()
        constraints = _empty_constraints()
        reasoning = "Supervisor parsing failed, full travel workflow selected as fallback."

    _update_agent_latency(metrics, "supervisor_agent", (time.time() - t0) * 1000)

    return {
        "guardrail_allowed": True,
        "guardrail_reason": guardrail_reason,
        "selected_agents": selected_agents,
        "trip_constraints": constraints,
        "supervisor_reasoning": reasoning,
        "messages": [AIMessage(content="Supervisor created the agent plan.")],
        "llm_calls": llm_calls,
        "metrics": metrics,
    }


async def guardrail_blocked_agent(state: TravelState):
    reason = state.get("final_response") or state.get("guardrail_reason") or "Request blocked by guardrail."
    return {
        "final_response": reason,
        "messages": [AIMessage(content=reason)],
    }


# =========================================================
# Specialist Agent Nodes
# =========================================================
FLIGHT_AGENT_PROMPT = """
You are a travel flight expert.

User Query: {query}
Airport Info: {airport_data}
Airline Info: {airline_data}

Generate: departure/arrival airports, airlines serving route, typical flight duration, airfare estimate, booking advice.
"""

async def flight_agent(state: TravelState):
    t0 = time.time()
    query = state["user_query"]
    metrics = state.get("metrics", {"agent_latencies": {}})

    try:
        airports = await aviation_mcp_call("list_airports")
        airlines = await aviation_mcp_call("list_airlines")
        prompt = FLIGHT_AGENT_PROMPT.format(
            query=query,
            airport_data=str(airports)[:3000],
            airline_data=str(airlines)[:3000],
        )
        response = await llm.ainvoke(
            [
                SystemMessage(content="You are an expert travel flight planner."),
                HumanMessage(content=prompt),
            ]
        )
        flight_data = response.content
    except Exception as exc:
        flight_data = f"Flight information unavailable: {exc}"

    _update_agent_latency(metrics, "flight_agent", (time.time() - t0) * 1000)
    return {
        "flight_results": flight_data,
        "messages": [AIMessage(content="Flight recommendations generated")],
        "llm_calls": state.get("llm_calls", 0) + 1,
        "metrics": metrics,
    }


async def hotel_agent(state: TravelState):
    t0 = time.time()
    query = f"Best hotels for {state['user_query']}"
    metrics = state.get("metrics", {"agent_latencies": {}})

    try:
        # Utilizing async TTL cache for Tavily web search
        hotel_results = await mcp_cache.get_or_set(
            "tavily_hotel",
            query,
            lambda: tavily_mcp_search(query),
        )
    except Exception as exc:
        print(f"HOTEL AGENT MCP ERROR: {exc}", flush=True)
        hotel_results = "Live hotel search is temporarily unavailable. Providing general neighborhood guidance."

    _update_agent_latency(metrics, "hotel_agent", (time.time() - t0) * 1000)
    return {
        "hotel_results": hotel_results,
        "messages": [AIMessage(content="Hotel information processed.")],
        "llm_calls": state.get("llm_calls", 0) + 1,
        "metrics": metrics,
    }


async def weather_agent(state: TravelState):
    t0 = time.time()
    city = await extract_destination(state["user_query"])
    metrics = state.get("metrics", {"agent_latencies": {}})

    try:
        # Utilizing async TTL cache for Weather MCP calls
        weather_data = await mcp_cache.get_or_set(
            "weather_current",
            city,
            lambda: weather_mcp_search(city),
        )
        forecast_data = await mcp_cache.get_or_set(
            "weather_forecast",
            city,
            lambda: forecast_mcp_search(city),
        )
        weather_results = f"Current Weather:\n{weather_data}\n\nForecast:\n{forecast_data}"
    except Exception as exc:
        print(f"WEATHER AGENT MCP ERROR: {exc}", flush=True)
        weather_results = f"Live weather for {city} is unavailable. General seasonal guidance provided."

    _update_agent_latency(metrics, "weather_agent", (time.time() - t0) * 1000)
    return {
        "weather_results": weather_results,
        "messages": [AIMessage(content="Weather information processed.")],
        "metrics": metrics,
    }


async def budget_agent(state: TravelState):
    t0 = time.time()
    metrics = state.get("metrics", {"agent_latencies": {}})

    prompt = f"""
Analyze whether this trip is realistic for the user's budget.
User Query: {state['user_query']}
Trip Constraints: {state.get('trip_constraints', {})}
Flight Results: {state.get('flight_results', '')}
Hotel Results: {state.get('hotel_results', '')}
Weather Results: {state.get('weather_results', '')}

Return: Cost breakdown, budget risks, money-saving tips, overall feasibility.
"""
    response = await llm.ainvoke(
        [
            SystemMessage(content="You are a practical travel budget analyst."),
            HumanMessage(content=prompt),
        ]
    )

    _update_agent_latency(metrics, "budget_agent", (time.time() - t0) * 1000)
    return {
        "budget_results": response.content,
        "messages": [AIMessage(content="Budget assessment generated.")],
        "llm_calls": state.get("llm_calls", 0) + 1,
        "metrics": metrics,
    }


# =========================================================
# Parallel Fan-Out Execution Node
# Executes selected specialist agents concurrently via asyncio.gather
# =========================================================
async def parallel_specialists_node(state: TravelState):
    t0 = time.time()
    selected = state.get("selected_agents", [])
    metrics = state.get("metrics", {"agent_latencies": {}})

    tasks = []
    task_keys = []

    if "flight_agent" in selected:
        tasks.append(flight_agent(state))
        task_keys.append("flight_results")

    if "hotel_agent" in selected:
        tasks.append(hotel_agent(state))
        task_keys.append("hotel_results")

    if "weather_agent" in selected:
        tasks.append(weather_agent(state))
        task_keys.append("weather_results")

    # Run selected agents concurrently in parallel!
    results = await asyncio.gather(*tasks, return_exceptions=True)

    updates: dict[str, Any] = {}
    additional_llm_calls = 0

    for key, res in zip(task_keys, results):
        if isinstance(res, Exception):
            print(f"Error in parallel execution of {key}: {res}")
            updates[key] = f"Information temporarily unavailable: {res}"
        elif isinstance(res, dict):
            updates[key] = res.get(key, "")
            additional_llm_calls += res.get("llm_calls", 0)
            if "metrics" in res and "agent_latencies" in res["metrics"]:
                metrics["agent_latencies"].update(res["metrics"]["agent_latencies"])

    # Run budget_agent after initial specialist data is gathered if requested
    if "budget_agent" in selected:
        temp_state = {**state, **updates}
        budget_res = await budget_agent(temp_state)
        updates["budget_results"] = budget_res.get("budget_results", "")
        additional_llm_calls += budget_res.get("llm_calls", 0)

    _update_agent_latency(metrics, "parallel_specialists_total", (time.time() - t0) * 1000)
    updates["llm_calls"] = state.get("llm_calls", 0) + additional_llm_calls
    updates["metrics"] = metrics
    return updates


# =========================================================
# Itinerary Agent
# =========================================================
async def itinerary_agent(state: TravelState):
    t0 = time.time()
    metrics = state.get("metrics", {"agent_latencies": {}})

    prompt = f"""
Create a complete travel itinerary.
User Query: {state['user_query']}
Constraints: {state.get('trip_constraints', {})}
Flights: {state.get('flight_results', '')}
Hotels: {state.get('hotel_results', '')}
Weather: {state.get('weather_results', '')}
Budget: {state.get('budget_results', '')}

Make the itinerary practical, budget-aware, and ready for human review.
"""

    response = await llm.ainvoke(
        [
            SystemMessage(content="You are an expert travel planner."),
            HumanMessage(content=prompt),
        ]
    )

    approval_request = "Please review the generated draft itinerary. Approve it to create the final polished plan, or provide feedback for revision."

    _update_agent_latency(metrics, "itinerary_agent", (time.time() - t0) * 1000)
    return {
        "itinerary": response.content,
        "approval_request": approval_request,
        "messages": [AIMessage(content="Draft itinerary created for human review.")],
        "llm_calls": state.get("llm_calls", 0) + 1,
        "metrics": metrics,
    }


# =========================================================
# Human Approval Node
# =========================================================
async def human_approval_agent(state: TravelState):
    review = interrupt(
        {
            "question": "Do you approve this itinerary?",
            "draft_itinerary": state.get("itinerary", ""),
            "approval_request": state.get("approval_request", ""),
            "selected_agents": state.get("selected_agents", []),
            "supervisor_reasoning": state.get("supervisor_reasoning", ""),
            "expected_response": {
                "approved": True,
                "feedback": "Optional revision feedback",
            },
        }
    )

    approved = bool(review.get("approved", False))
    human_feedback = str(review.get("feedback", "")).strip()

    return {
        "approved": approved,
        "human_feedback": human_feedback,
        "messages": [AIMessage(content="Human approval step completed.")],
    }


# =========================================================
# Final Response Agent
# =========================================================
async def final_agent(state: TravelState):
    t0 = time.time()
    metrics = state.get("metrics", {"agent_latencies": {}})

    if state.get("approved", False):
        review_instruction = "The user approved the draft. Preserve its decisions while polishing it."
    else:
        review_instruction = f"The user requested a revision. Apply this feedback carefully: {state.get('human_feedback', '')}"

    final_prompt = f"""
Generate the final travel response for the user.
Human Review: {review_instruction}
User Request: {state['user_query']}
Constraints: {state.get('trip_constraints', {})}
Flights: {state.get('flight_results', '')}
Hotels: {state.get('hotel_results', '')}
Weather: {state.get('weather_results', '')}
Budget: {state.get('budget_results', '')}
Draft Itinerary: {state.get('itinerary', '')}

Format final answer with sections:
1. Trip Summary
2. Flight Information
3. Hotel Suggestions
4. Weather Information
5. Day-by-Day Itinerary
6. Estimated Budget
7. Final Recommendations
"""

    response = await llm.ainvoke(
        [
            SystemMessage(content="You are a professional AI travel booking assistant."),
            HumanMessage(content=final_prompt),
        ]
    )

    _update_agent_latency(metrics, "final_agent", (time.time() - t0) * 1000)
    
    # Calculate overall workflow latency
    start_time = state.get("start_time", time.time())
    metrics["total_latency_ms"] = round((time.time() - start_time) * 1000, 2)
    metrics["cache_stats"] = mcp_cache.get_stats()

    return {
        "final_response": response.content,
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1,
        "metrics": metrics,
    }


# =========================================================
# Dynamic Supervisor Routing
# =========================================================
ROUTE_MAP = {
    "guardrail_blocked": "guardrail_blocked",
    "parallel_specialists": "parallel_specialists",
    "itinerary_agent": "itinerary_agent",
}


def route_from_supervisor(state: TravelState) -> str:
    if not state.get("guardrail_allowed", True):
        return "guardrail_blocked"
    return "parallel_specialists"


# =========================================================
# Build State Graph
# =========================================================
graph = StateGraph(TravelState)

graph.add_node("supervisor", supervisor_agent)
graph.add_node("guardrail_blocked", guardrail_blocked_agent)
graph.add_node("parallel_specialists", parallel_specialists_node)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("human_approval", human_approval_agent)
graph.add_node("final_agent", final_agent)

# Kept individual nodes for standalone testing / granular inspection
graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("weather_agent", weather_agent)
graph.add_node("budget_agent", budget_agent)

graph.add_edge(START, "supervisor")
graph.add_conditional_edges("supervisor", route_from_supervisor, ROUTE_MAP)
graph.add_edge("parallel_specialists", "itinerary_agent")
graph.add_edge("itinerary_agent", "human_approval")
graph.add_edge("human_approval", "final_agent")
graph.add_edge("final_agent", END)
graph.add_edge("guardrail_blocked", END)

# Checkpointer setup
try:
    DATABASE_URL = get_database_url()
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not set.")
    _conn = psycopg.connect(
        DATABASE_URL,
        autocommit=True,
        row_factory=dict_row,
    )
    checkpointer = PostgresSaver(_conn)
    checkpointer.setup()
except Exception as exc:
    print(f"PostgreSQL checkpointer fallback to MemorySaver ({exc})")
    from langgraph.checkpoint.memory import MemorySaver
    checkpointer = MemorySaver()

travel_graph = graph.compile(checkpointer=checkpointer)


# =========================================================
# FastAPI-Facing Serialization Helpers
# =========================================================
def _interrupt_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    interrupts = result.get("__interrupt__", [])
    if not interrupts:
        return None
    first_interrupt = interrupts[0]
    payload = getattr(first_interrupt, "value", first_interrupt)
    return payload if isinstance(payload, dict) else {"value": payload}


def _serialize_result(
    result: dict[str, Any],
    thread_id: str,
) -> dict[str, Any]:
    messages = result.get("messages", [])
    last_message = messages[-1].content if messages else ""
    answer = result.get("final_response") or last_message
    interrupt_payload = _interrupt_payload(result)

    if interrupt_payload:
        answer = interrupt_payload.get("draft_itinerary") or result.get("itinerary", "")

    return {
        "thread_id": thread_id,
        "answer": answer,
        "requires_approval": interrupt_payload is not None,
        "approval_request": (
            interrupt_payload.get("approval_request", "")
            if interrupt_payload
            else result.get("approval_request", "")
        ),
        "flight_results": result.get("flight_results", ""),
        "hotel_results": result.get("hotel_results", ""),
        "weather_results": result.get("weather_results", ""),
        "budget_results": result.get("budget_results", ""),
        "itinerary": (
            interrupt_payload.get("draft_itinerary", "")
            if interrupt_payload
            else result.get("itinerary", "")
        ),
        "selected_agents": result.get("selected_agents", []),
        "trip_constraints": result.get("trip_constraints", {}),
        "supervisor_reasoning": result.get("supervisor_reasoning", ""),
        "guardrail_allowed": result.get("guardrail_allowed", True),
        "guardrail_reason": result.get("guardrail_reason", ""),
        "approved": result.get("approved"),
        "human_feedback": result.get("human_feedback", ""),
        "llm_calls": result.get("llm_calls", 0),
        "metrics": result.get("metrics", {}),
    }


async def run_travel_agent(user_input: str, thread_id: str | None = None):
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    config = {"configurable": {"thread_id": thread_id}}
    t0 = time.time()

    result = await travel_graph.ainvoke(
        {
            "messages": [HumanMessage(content=user_input)],
            "user_query": user_input,
            "guardrail_allowed": True,
            "guardrail_reason": "",
            "selected_agents": [],
            "trip_constraints": _empty_constraints(),
            "supervisor_reasoning": "",
            "flight_results": "",
            "hotel_results": "",
            "weather_results": "",
            "budget_results": "",
            "itinerary": "",
            "approval_request": "",
            "approved": False,
            "human_feedback": "",
            "final_response": "",
            "llm_calls": 0,
            "start_time": t0,
            "metrics": {"agent_latencies": {}, "total_latency_ms": 0.0},
        },
        config=config,
    )

    return _serialize_result(result, thread_id)


async def resume_travel_agent(
    thread_id: str,
    approved: bool,
    feedback: str = "",
):
    if not thread_id:
        raise ValueError("thread_id is required to resume a travel plan.")

    config = {"configurable": {"thread_id": thread_id}}
    result = await travel_graph.ainvoke(
        Command(
            resume={
                "approved": approved,
                "feedback": feedback.strip(),
            }
        ),
        config=config,
    )

    return _serialize_result(result, thread_id)