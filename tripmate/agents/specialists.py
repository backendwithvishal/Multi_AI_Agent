from langchain_core.messages import SystemMessage, HumanMessage
from tripmate.integrations.mcp import safe_aviation_call, safe_tavily_search, safe_weather_search, safe_extract_destination
from tripmate.cache.ttl_cache import app_cache


async def run_flight_agent(llm, user_query: str) -> str:
    try:
        airports = await safe_aviation_call("list_airports")
        airlines = await safe_aviation_call("list_airlines")
        
        prompt = f"""
User Query: {user_query}
Airport Info: {str(airports)[:2000]}
Airline Info: {str(airlines)[:2000]}

Provide flight advice: departure/arrival airport options, airlines, estimated airfare, booking tips.
"""
        if not llm:
            return "Flight Analysis: Sample flight routes identified."

        response = await llm.ainvoke(
            [
                SystemMessage(content="You are an expert travel flight planner."),
                HumanMessage(content=prompt),
            ]
        )
        return str(response.content)
    except Exception as exc:
        return f"Flight information notice: {exc}"


async def run_hotel_agent(llm, user_query: str) -> str:
    query = f"Best hotels for {user_query}"
    try:
        hotel_data = await app_cache.get_or_set(
            "tavily_hotel",
            query,
            lambda: safe_tavily_search(query),
        )
        return str(hotel_data)
    except Exception as exc:
        return f"Hotel information notice: {exc}"


async def run_weather_agent(llm, user_query: str) -> str:
    try:
        city = await safe_extract_destination(user_query)
        weather_data = await app_cache.get_or_set(
            "weather_search",
            city,
            lambda: safe_weather_search(city),
        )
        return str(weather_data)
    except Exception as exc:
        return f"Weather information notice: {exc}"


async def run_budget_agent(llm, user_query: str, constraints: dict, flight_info: str, hotel_info: str, weather_info: str) -> str:
    if not llm:
        return "Budget Assessment: Trip appears budget-feasible."

    prompt = f"""
User Query: {user_query}
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
        return str(response.content)
    except Exception as exc:
        return f"Budget assessment notice: {exc}"


async def run_itinerary_agent(llm, user_query: str, constraints: dict, flight_info: str, hotel_info: str, weather_info: str, budget_info: str) -> str:
    if not llm:
        return "Draft Itinerary: 5-Day Travel Plan ready for review."

    prompt = f"""
User Query: {user_query}
Constraints: {constraints}
Flights: {flight_info}
Hotels: {hotel_info}
Weather: {weather_info}
Budget: {budget_info}

Create a clear, practical day-by-day draft itinerary ready for human review.
"""
    try:
        response = await llm.ainvoke(
            [
                SystemMessage(content="You are an expert travel planner."),
                HumanMessage(content=prompt),
            ]
        )
        return str(response.content)
    except Exception as exc:
        return f"Itinerary drafting notice: {exc}"


async def run_final_agent(llm, user_query: str, state_data: dict) -> str:
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
