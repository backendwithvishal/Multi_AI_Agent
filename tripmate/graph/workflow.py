import asyncio
import time
from typing import Any, Dict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from langchain_core.messages import AIMessage

from tripmate.graph.state import TravelState
from tripmate.graph.routing import route_from_supervisor, ROUTE_MAP
from tripmate.agents.guardrail import run_guardrail_check
from tripmate.agents.supervisor import run_supervisor_routing
from tripmate.agents.specialists import (
    run_flight_agent,
    run_hotel_agent,
    run_weather_agent,
    run_budget_agent,
    run_itinerary_agent,
    run_final_agent,
)
from tripmate.database import checkpointer
from tripmate.config.settings import settings

try:
    from langchain_groq import ChatGroq
    if settings.GROQ_API_KEY:
        llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=settings.GROQ_API_KEY)
    else:
        llm = None
except Exception:
    llm = None


def _update_latency(metrics: dict, name: str, latency_ms: float):
    agent_latencies = metrics.get("agent_latencies", {})
    agent_latencies[name] = round(latency_ms, 2)
    metrics["agent_latencies"] = agent_latencies


async def supervisor_node(state: TravelState):
    t0 = time.time()
    query = state["user_query"]
    metrics = state.get("metrics", {"agent_latencies": {}, "total_latency_ms": 0.0})

    allowed, reason = await run_guardrail_check(llm, query)
    if not allowed:
        _update_latency(metrics, "guardrail", (time.time() - t0) * 1000)
        return {
            "status": "BLOCKED",
            "guardrail_allowed": False,
            "guardrail_reason": reason,
            "selected_agents": [],
            "supervisor_reasoning": reason,
            "final_response": reason,
            "messages": [AIMessage(content=f"Guardrail blocked request: {reason}")],
            "metrics": metrics,
        }

    routing = await run_supervisor_routing(llm, query)
    _update_latency(metrics, "supervisor", (time.time() - t0) * 1000)

    return {
        "status": "RUNNING",
        "guardrail_allowed": True,
        "guardrail_reason": reason,
        "selected_agents": routing.selected_agents,
        "trip_constraints": routing.trip_constraints.model_dump(),
        "supervisor_reasoning": routing.reasoning,
        "messages": [AIMessage(content="Supervisor node routing created.")],
        "metrics": metrics,
    }


async def guardrail_blocked_node(state: TravelState):
    reason = state.get("final_response") or state.get("guardrail_reason") or "Request blocked by input guardrail."
    return {
        "status": "BLOCKED",
        "final_response": reason,
        "messages": [AIMessage(content=reason)],
    }


async def parallel_specialists_node(state: TravelState):
    t0 = time.time()
    selected = state.get("selected_agents", [])
    query = state["user_query"]
    metrics = state.get("metrics", {"agent_latencies": {}})

    tasks = []
    task_keys = []

    if "flight_agent" in selected:
        tasks.append(run_flight_agent(llm, query))
        task_keys.append("flight_results")

    if "hotel_agent" in selected:
        tasks.append(run_hotel_agent(llm, query))
        task_keys.append("hotel_results")

    if "weather_agent" in selected:
        tasks.append(run_weather_agent(llm, query))
        task_keys.append("weather_results")

    results = await asyncio.gather(*tasks, return_exceptions=True)

    updates: Dict[str, Any] = {}
    for key, res in zip(task_keys, results):
        if isinstance(res, Exception):
            updates[key] = f"Provider unavailable: {res}"
        else:
            updates[key] = str(res)

    if "budget_agent" in selected:
        constraints = state.get("trip_constraints", {})
        budget_res = await run_budget_agent(
            llm, query, constraints,
            updates.get("flight_results", ""),
            updates.get("hotel_results", ""),
            updates.get("weather_results", "")
        )
        updates["budget_results"] = budget_res

    _update_latency(metrics, "parallel_specialists", (time.time() - t0) * 1000)
    _update_latency(metrics, "parallel_specialists_total", (time.time() - t0) * 1000)
    updates["metrics"] = metrics
    return updates


async def itinerary_node(state: TravelState):
    t0 = time.time()
    metrics = state.get("metrics", {"agent_latencies": {}})

    itinerary_res = await run_itinerary_agent(
        llm,
        state["user_query"],
        state.get("trip_constraints", {}),
        state.get("flight_results", ""),
        state.get("hotel_results", ""),
        state.get("weather_results", ""),
        state.get("budget_results", ""),
    )

    _update_latency(metrics, "itinerary_agent", (time.time() - t0) * 1000)
    return {
        "status": "WAITING_FOR_APPROVAL",
        "itinerary": itinerary_res,
        "approval_request": "Please review draft itinerary and approve or provide revision feedback.",
        "messages": [AIMessage(content="Draft itinerary synthesized.")],
        "metrics": metrics,
    }


async def human_approval_node(state: TravelState):
    review = interrupt(
        {
            "question": "Do you approve this itinerary?",
            "draft_itinerary": state.get("itinerary", ""),
            "approval_request": state.get("approval_request", ""),
            "expected_response": {"approved": True, "feedback": "Optional revision feedback"},
        }
    )

    approved = bool(review.get("approved", False))
    feedback = str(review.get("feedback", "")).strip()

    return {
        "status": "APPROVED" if approved else "REVISION_REQUESTED",
        "approved": approved,
        "human_feedback": feedback,
        "messages": [AIMessage(content="Human approval step completed.")],
    }


async def final_node(state: TravelState):
    t0 = time.time()
    metrics = state.get("metrics", {"agent_latencies": {}})

    final_res = await run_final_agent(llm, state["user_query"], state)
    _update_latency(metrics, "final_agent", (time.time() - t0) * 1000)

    start_time = state.get("start_time", time.time())
    metrics["total_latency_ms"] = round((time.time() - start_time) * 1000, 2)

    return {
        "status": "COMPLETED",
        "final_response": final_res,
        "messages": [AIMessage(content=final_res)],
        "metrics": metrics,
    }


builder = StateGraph(TravelState)

builder.add_node("supervisor", supervisor_node)
builder.add_node("guardrail_blocked", guardrail_blocked_node)
builder.add_node("parallel_specialists", parallel_specialists_node)
builder.add_node("itinerary_agent", itinerary_node)
builder.add_node("human_approval", human_approval_node)
builder.add_node("final_agent", final_node)

builder.add_edge(START, "supervisor")
builder.add_conditional_edges("supervisor", route_from_supervisor, ROUTE_MAP)
builder.add_edge("parallel_specialists", "itinerary_agent")
builder.add_edge("itinerary_agent", "human_approval")
builder.add_edge("human_approval", "final_agent")
builder.add_edge("final_agent", END)
builder.add_edge("guardrail_blocked", END)

travel_workflow_graph = builder.compile(checkpointer=checkpointer)
