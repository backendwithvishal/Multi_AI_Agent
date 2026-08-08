"""
Specialist AI Agents Module

This file implements domain-specific travel agents registered in AgentRegistry:
- `FlightAgent`: Queries AviationStack MCP for airports/airlines & recommends flights.
- `HotelAgent`: Queries Tavily Search MCP for hotel accommodations & prices.
- `WeatherAgent`: Queries OpenWeather MCP for current weather & forecast.
- `BudgetAgent`: Calculates trip costs, budget feasibility, and savings tips.
- `ItineraryAgent`: Synthesizes outputs into a day-by-day draft itinerary.
- `FinalAgent`: Formats final approved travel plan response for the client.

All agents produce `StructuredAgentOutput` objects with evidence metadata and confidence scores.
"""

import time
from typing import Any, Dict, Optional
from langchain_core.messages import SystemMessage, HumanMessage

from tripmate.schemas.agents import (
    StructuredAgentOutput,
    EvidenceItem,
    EvidenceType,
    VerificationStatus,
)
from tripmate.agents.registry import BaseAgent, AgentMetadata, agent_registry
from tripmate.integrations.mcp import (
    safe_aviation_call,
    safe_tavily_search,
    safe_weather_search,
    safe_extract_destination,
)
from tripmate.cache.redis_cache import hybrid_cache


# =========================================================
# Flight Agent
# =========================================================

class FlightAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentMetadata(
                name="flight_agent",
                description="Fetches flight status, airport locations, airline details, and pricing estimates.",
                capabilities=["airports", "airlines", "flight_routes", "pricing"],
                required_tools=["safe_aviation_call"],
                risk_level="low",
            )
        )

    async def run(self, llm: Any, query: str, context: Optional[Dict[str, Any]] = None) -> StructuredAgentOutput:
        t0 = time.time()
        try:
            airports = await safe_aviation_call("list_airports")
            airlines = await safe_aviation_call("list_airlines")
            
            prompt = f"""
User Query: {query}
Airport Info: {str(airports)[:2000]}
Airline Info: {str(airlines)[:2000]}

Provide flight advice: departure/arrival airport options, airlines, estimated airfare, booking tips.
"""
            if not llm:
                result_text = "Flight Analysis: Sample flight routes identified."
                evidence = EvidenceItem(
                    source_name="AviationStack MCP",
                    source_type=EvidenceType.FALLBACK,
                    status=VerificationStatus.UNCERTAIN,
                    confidence=0.6,
                    details="LLM unconfigured default response.",
                )
            else:
                response = await llm.ainvoke(
                    [
                        SystemMessage(content="You are an expert travel flight planner."),
                        HumanMessage(content=prompt),
                    ]
                )
                result_text = str(response.content)
                evidence = EvidenceItem(
                    source_name="AviationStack MCP",
                    source_type=EvidenceType.API,
                    status=VerificationStatus.VERIFIED,
                    confidence=0.92,
                    details="Live aviation data queried.",
                )

            return StructuredAgentOutput(
                agent_name=self.name,
                status="success",
                result=result_text,
                confidence=evidence.confidence,
                sources=[evidence],
                execution_time_ms=round((time.time() - t0) * 1000, 2),
            )
        except Exception as exc:
            return StructuredAgentOutput(
                agent_name=self.name,
                status="degraded",
                result=f"Flight information notice: {exc}",
                confidence=0.4,
                sources=[
                    EvidenceItem(
                        source_name="AviationStack MCP",
                        source_type=EvidenceType.FALLBACK,
                        status=VerificationStatus.UNAVAILABLE,
                        confidence=0.3,
                        details=str(exc),
                    )
                ],
                warnings=[str(exc)],
                execution_time_ms=round((time.time() - t0) * 1000, 2),
            )


# =========================================================
# Hotel Agent
# =========================================================

class HotelAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentMetadata(
                name="hotel_agent",
                description="Searches live hotel accommodations, amenities, and room pricing.",
                capabilities=["hotels", "resorts", "accommodations", "pricing"],
                required_tools=["safe_tavily_search"],
                risk_level="low",
            )
        )

    async def run(self, llm: Any, query: str, context: Optional[Dict[str, Any]] = None) -> StructuredAgentOutput:
        t0 = time.time()
        search_query = f"Best hotels for {query}"
        try:
            hotel_data = await hybrid_cache.get_or_set(
                "tavily_hotel",
                search_query,
                lambda: safe_tavily_search(search_query),
            )
            return StructuredAgentOutput(
                agent_name=self.name,
                status="success",
                result=str(hotel_data),
                confidence=0.90,
                sources=[
                    EvidenceItem(
                        source_name="Tavily Search MCP",
                        source_type=EvidenceType.WEB_SEARCH,
                        status=VerificationStatus.VERIFIED,
                        confidence=0.90,
                        details="Live hotel web search executed.",
                    )
                ],
                execution_time_ms=round((time.time() - t0) * 1000, 2),
            )
        except Exception as exc:
            return StructuredAgentOutput(
                agent_name=self.name,
                status="degraded",
                result=f"Hotel information notice: {exc}",
                confidence=0.4,
                warnings=[str(exc)],
                execution_time_ms=round((time.time() - t0) * 1000, 2),
            )


# =========================================================
# Weather Agent
# =========================================================

class WeatherAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentMetadata(
                name="weather_agent",
                description="Fetches live current weather conditions and 5-day forecasts.",
                capabilities=["current_weather", "forecast", "climate"],
                required_tools=["safe_weather_search"],
                risk_level="low",
            )
        )

    async def run(self, llm: Any, query: str, context: Optional[Dict[str, Any]] = None) -> StructuredAgentOutput:
        t0 = time.time()
        try:
            city = await safe_extract_destination(query)
            weather_data = await hybrid_cache.get_or_set(
                "weather_search",
                city,
                lambda: safe_weather_search(city),
            )
            return StructuredAgentOutput(
                agent_name=self.name,
                status="success",
                result=str(weather_data),
                confidence=0.95,
                sources=[
                    EvidenceItem(
                        source_name="OpenWeather FastMCP",
                        source_type=EvidenceType.API,
                        status=VerificationStatus.VERIFIED,
                        confidence=0.95,
                        details=f"Weather metrics retrieved for {city}.",
                    )
                ],
                execution_time_ms=round((time.time() - t0) * 1000, 2),
            )
        except Exception as exc:
            return StructuredAgentOutput(
                agent_name=self.name,
                status="degraded",
                result=f"Weather information notice: {exc}",
                confidence=0.4,
                warnings=[str(exc)],
                execution_time_ms=round((time.time() - t0) * 1000, 2),
            )


# =========================================================
# Budget Agent
# =========================================================

class BudgetAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentMetadata(
                name="budget_agent",
                description="Evaluates budget feasibility, cost estimates, and money-saving strategies.",
                capabilities=["cost_estimation", "budget_validation", "savings_tips"],
                required_tools=[],
                risk_level="low",
            )
        )

    async def run(self, llm: Any, query: str, context: Optional[Dict[str, Any]] = None) -> StructuredAgentOutput:
        t0 = time.time()
        context = context or {}
        constraints = context.get("constraints", {})
        flight_info = context.get("flight_info", "")
        hotel_info = context.get("hotel_info", "")
        weather_info = context.get("weather_info", "")

        if not llm:
            return StructuredAgentOutput(
                agent_name=self.name,
                status="success",
                result="Budget Assessment: Trip appears budget-feasible.",
                confidence=0.7,
                sources=[
                    EvidenceItem(
                        source_name="Budget Heuristics",
                        source_type=EvidenceType.LLM_ESTIMATE,
                        status=VerificationStatus.ESTIMATED,
                        confidence=0.7,
                    )
                ],
                execution_time_ms=round((time.time() - t0) * 1000, 2),
            )

        prompt = f"""
User Query: {query}
Constraints: {constraints}
Flight Results: {flight_info}
Hotel Results: {hotel_info}
Weather Results: {weather_info}

Analyze budget feasibility, cost estimates, risk areas, and money-saving tips.
"""
        try:
            response = await llm.ainvoke(
                [
                    SystemMessage(content="You are a practical travel budget analyst."),
                    HumanMessage(content=prompt),
                ]
            )
            return StructuredAgentOutput(
                agent_name=self.name,
                status="success",
                result=str(response.content),
                confidence=0.88,
                sources=[
                    EvidenceItem(
                        source_name="Budget Synthesis LLM",
                        source_type=EvidenceType.LLM_ESTIMATE,
                        status=VerificationStatus.ESTIMATED,
                        confidence=0.88,
                    )
                ],
                execution_time_ms=round((time.time() - t0) * 1000, 2),
            )
        except Exception as exc:
            return StructuredAgentOutput(
                agent_name=self.name,
                status="degraded",
                result=f"Budget assessment notice: {exc}",
                confidence=0.4,
                warnings=[str(exc)],
                execution_time_ms=round((time.time() - t0) * 1000, 2),
            )


# =========================================================
# Itinerary Agent
# =========================================================

class ItineraryAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentMetadata(
                name="itinerary_agent",
                description="Synthesizes flights, hotels, weather, and budget data into a cohesive draft itinerary.",
                capabilities=["itinerary_synthesis", "day_planning", "schedule_optimization"],
                required_tools=[],
                risk_level="medium",
            )
        )

    async def run(self, llm: Any, query: str, context: Optional[Dict[str, Any]] = None) -> StructuredAgentOutput:
        t0 = time.time()
        context = context or {}
        if not llm:
            return StructuredAgentOutput(
                agent_name=self.name,
                status="success",
                result="Draft Itinerary: 5-Day Travel Plan ready for review.",
                confidence=0.7,
                execution_time_ms=round((time.time() - t0) * 1000, 2),
            )

        prompt = f"""
User Query: {query}
Constraints: {context.get('constraints', {})}
Flights: {context.get('flight_info', '')}
Hotels: {context.get('hotel_info', '')}
Weather: {context.get('weather_info', '')}
Budget: {context.get('budget_info', '')}

Create a clear, practical day-by-day draft itinerary ready for human review.
"""
        try:
            response = await llm.ainvoke(
                [
                    SystemMessage(content="You are an expert travel planner."),
                    HumanMessage(content=prompt),
                ]
            )
            return StructuredAgentOutput(
                agent_name=self.name,
                status="success",
                result=str(response.content),
                confidence=0.90,
                sources=[
                    EvidenceItem(
                        source_name="Multi-Agent Synthesis Engine",
                        source_type=EvidenceType.LLM_ESTIMATE,
                        status=VerificationStatus.ESTIMATED,
                        confidence=0.90,
                    )
                ],
                execution_time_ms=round((time.time() - t0) * 1000, 2),
            )
        except Exception as exc:
            return StructuredAgentOutput(
                agent_name=self.name,
                status="degraded",
                result=f"Itinerary drafting notice: {exc}",
                confidence=0.4,
                warnings=[str(exc)],
                execution_time_ms=round((time.time() - t0) * 1000, 2),
            )


# Register agent singletons into AgentRegistry
flight_agent_obj = FlightAgent()
hotel_agent_obj = HotelAgent()
weather_agent_obj = WeatherAgent()
budget_agent_obj = BudgetAgent()
itinerary_agent_obj = ItineraryAgent()

agent_registry.register(flight_agent_obj)
agent_registry.register(hotel_agent_obj)
agent_registry.register(weather_agent_obj)
agent_registry.register(budget_agent_obj)
agent_registry.register(itinerary_agent_obj)


# =========================================================
# Backward-Compatible Async Runner Functions
# =========================================================

async def run_flight_agent(llm: Any, user_query: str) -> str:
    output = await flight_agent_obj.run(llm, user_query)
    return str(output.result)


async def run_hotel_agent(llm: Any, user_query: str) -> str:
    output = await hotel_agent_obj.run(llm, user_query)
    return str(output.result)


async def run_weather_agent(llm: Any, user_query: str) -> str:
    output = await weather_agent_obj.run(llm, user_query)
    return str(output.result)


async def run_budget_agent(llm: Any, user_query: str, constraints: dict, flight_info: str, hotel_info: str, weather_info: str) -> str:
    output = await budget_agent_obj.run(
        llm,
        user_query,
        context={
            "constraints": constraints,
            "flight_info": flight_info,
            "hotel_info": hotel_info,
            "weather_info": weather_info,
        },
    )
    return str(output.result)


async def run_itinerary_agent(llm: Any, user_query: str, constraints: dict, flight_info: str, hotel_info: str, weather_info: str, budget_info: str) -> str:
    output = await itinerary_agent_obj.run(
        llm,
        user_query,
        context={
            "constraints": constraints,
            "flight_info": flight_info,
            "hotel_info": hotel_info,
            "weather_info": weather_info,
            "budget_info": budget_info,
        },
    )
    return str(output.result)


async def run_final_agent(llm: Any, user_query: str, state_data: dict) -> str:
    """Specialist Agent: Generates final polished travel response after HITL review."""
    if not llm:
        return state_data.get("itinerary", "Final Polished Travel Plan.")

    approved = state_data.get("approved", False)
    feedback = state_data.get("human_feedback", "")
    review_note = "User approved the draft itinerary." if approved else f"Apply revision feedback: {feedback}"

    prompt = f"""
Generate final polished travel response.
Review Note: {review_note}
User Request: {user_query}
Constraints: {state_data.get('trip_constraints', {})}
Flights: {state_data.get('flight_results', '')}
Hotels: {state_data.get('hotel_results', '')}
Weather: {state_data.get('weather_results', '')}
Budget Analysis: {state_data.get('budget_results', '')}
Draft Itinerary: {state_data.get('itinerary', '')}

Format final output with clear sections:
1. Trip Summary
2. Flight Information
3. Hotel Suggestions
4. Weather Advice
5. Day-by-Day Itinerary
6. Estimated Budget
7. Final Recommendations
"""
    try:
        response = await llm.ainvoke(
            [
                SystemMessage(content="You are a professional AI travel booking assistant."),
                HumanMessage(content=prompt),
            ]
        )
        return str(response.content)
    except Exception as exc:
        return state_data.get("itinerary", f"Final plan generated with notice: {exc}")
