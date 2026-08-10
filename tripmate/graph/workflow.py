"""
LangGraph Workflow Assembly Module

This file constructs the complete dynamic multi-agent execution graph:
1. `supervisor`: Evaluates guardrail safety and generates dynamic task DAG plan.
2. `parallel_specialists`: Executes independent specialist agents concurrently.
3. `critic`: Validates gathered specialist data and checks constraint compliance.
4. `itinerary_agent`: Synthesizes validated data into a day-by-day draft itinerary.
5. `human_approval`: Triggers a LangGraph state interrupt for Human-in-the-Loop review.
6. `final_agent`: Formats and finishes the final travel response.
"""

import asyncio
import time
from typing import Any, Dict, List
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from langchain_core.messages import AIMessage

from tripmate.graph.state import TravelState
from tripmate.graph.routing import route_from_supervisor, ROUTE_MAP
from tripmate.agents.guardrail import run_guardrail_check
from tripmate.agents.supervisor import run_supervisor_routing
from tripmate.agents.critic import critic_agent
from tripmate.agents.specialists import (
    flight_agent_obj,
    hotel_agent_obj,
    weather_agent_obj,
    budget_agent_obj,
    itinerary_agent_obj,
    run_final_agent,
)
from tripmate.services.model_router import model_router, ModelTier
from tripmate.database import checkpointer


def _update_latency(metrics: dict, name: str, latency_ms: float):
    agent_latencies = metrics.get("agent_latencies", {})
    agent_latencies[name] = round(latency_ms, 2)
    metrics["agent_latencies"] = agent_latencies


async def supervisor_node(state: TravelState):
    t0 = time.time()
    query = state["user_query"]
    metrics = state.get("metrics", {"agent_latencies": {}, "total_latency_ms": 0.0})

    fast_llm = model_router.get_model(ModelTier.FAST)
    reasoning_llm = model_router.get_model(ModelTier.REASONING)

    allowed, reason = await run_guardrail_check(fast_llm or reasoning_llm, query)
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

    routing = await run_supervisor_routing(reasoning_llm, query)
    _update_latency(metrics, "supervisor", (time.time() - t0) * 1000)

    return {
        "status": "RUNNING",
        "guardrail_allowed": True,
        "guardrail_reason": reason,
        "selected_agents": routing.selected_agents,
        "trip_constraints": routing.trip_constraints.model_dump(),
        "supervisor_reasoning": routing.reasoning,
        "messages": [AIMessage(content="Supervisor node routing completed.")],
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

    reasoning_llm = model_router.get_model(ModelTier.REASONING)

    tasks = []
    task_keys = []
    agent_instances = []

    if "flight_agent" in selected:
        tasks.append(flight_agent_obj.run(reasoning_llm, query))
        task_keys.append("flight_results")
        agent_instances.append("flight_agent")

    if "hotel_agent" in selected:
        tasks.append(hotel_agent_obj.run(reasoning_llm, query))
        task_keys.append("hotel_results")
        agent_instances.append("hotel_agent")

    if "weather_agent" in selected:
        tasks.append(weather_agent_obj.run(reasoning_llm, query))
        task_keys.append("weather_results")
        agent_instances.append("weather_agent")

    results = await asyncio.gather(*tasks, return_exceptions=True)

    updates: Dict[str, Any] = {}
    structured_map: Dict[str, Any] = state.get("structured_outputs", {})
    evidence_list: List[Dict[str, Any]] = state.get("evidence_items", [])

    for key, agent_name, res in zip(task_keys, agent_instances, results):
        if isinstance(res, Exception):
            updates[key] = f"Provider unavailable: {res}"
        else:
            updates[key] = str(res.result)
            structured_map[agent_name] = res.model_dump(mode="json")
            for src in res.sources:
                evidence_list.append(src.model_dump(mode="json"))

    if "budget_agent" in selected:
        constraints = state.get("trip_constraints", {})
        budget_output = await budget_agent_obj.run(
            reasoning_llm,
            query,
            context={
                "constraints": constraints,
                "flight_info": updates.get("flight_results", ""),
                "hotel_info": updates.get("hotel_results", ""),
                "weather_info": updates.get("weather_results", ""),
            },
        )
        updates["budget_results"] = str(budget_output.result)
        structured_map["budget_agent"] = budget_output.model_dump(mode="json")
        for src in budget_output.sources:
            evidence_list.append(src.model_dump(mode="json"))

    _update_latency(metrics, "parallel_specialists", (time.time() - t0) * 1000)
    _update_latency(metrics, "parallel_specialists_total", (time.time() - t0) * 1000)
    updates["metrics"] = metrics
    updates["structured_outputs"] = structured_map
    updates["evidence_items"] = evidence_list
    return updates


async def critic_node(state: TravelState):
    t0 = time.time()
    metrics = state.get("metrics", {"agent_latencies": {}})
    query = state["user_query"]
    constraints = state.get("trip_constraints", {})
    outputs = {
        "flight_results": state.get("flight_results", ""),
        "hotel_results": state.get("hotel_results", ""),
        "weather_results": state.get("weather_results", ""),
        "budget_results": state.get("budget_results", ""),
    }

    reasoning_llm = model_router.get_model(ModelTier.REASONING)
    report = await critic_agent.evaluate_plan(
        reasoning_llm,
        query,
        constraints,
        outputs,
        state.get("itinerary", ""),
    )

    _update_latency(metrics, "critic_agent", (time.time() - t0) * 1000)
    return {
        "critic_report": report.model_dump(mode="json"),
        "metrics": metrics,
    }


async def itinerary_node(state: TravelState):
    t0 = time.time()
    metrics = state.get("metrics", {"agent_latencies": {}})
    reasoning_llm = model_router.get_model(ModelTier.REASONING)

    itinerary_output = await itinerary_agent_obj.run(
        reasoning_llm,
        state["user_query"],
        context={
            "constraints": state.get("trip_constraints", {}),
            "flight_info": state.get("flight_results", ""),
            "hotel_info": state.get("hotel_results", ""),
            "weather_info": state.get("weather_results", ""),
            "budget_info": state.get("budget_results", ""),
        },
    )

    _update_latency(metrics, "itinerary_agent", (time.time() - t0) * 1000)
    return {
        "status": "WAITING_FOR_APPROVAL",
        "itinerary": str(itinerary_output.result),
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
    reasoning_llm = model_router.get_model(ModelTier.REASONING)

    final_res = await run_final_agent(reasoning_llm, state["user_query"], state)
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
builder.add_node("critic", critic_node)
builder.add_node("itinerary_agent", itinerary_node)
builder.add_node("human_approval", human_approval_node)
builder.add_node("final_agent", final_node)

builder.add_edge(START, "supervisor")
builder.add_conditional_edges("supervisor", route_from_supervisor, ROUTE_MAP)
builder.add_edge("parallel_specialists", "critic")
builder.add_edge("critic", "itinerary_agent")
builder.add_edge("itinerary_agent", "human_approval")
builder.add_edge("human_approval", "final_agent")
builder.add_edge("final_agent", END)
builder.add_edge("guardrail_blocked", END)

travel_workflow_graph = builder.compile(checkpointer=checkpointer)
