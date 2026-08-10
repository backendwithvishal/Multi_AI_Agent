"""
MultiServerMCPClient Connection Manager

This module manages connections to all Model Context Protocol (MCP) servers:
1. Tavily MCP Server (HTTP Streamable transport for live web hotel searches).
2. AviationStack MCP Server (stdio transport for live flight status and airport data).
3. Custom Weather FastMCP Server (stdio transport for OpenWeather current & forecast metrics).
"""

import os
import shutil
import sys
from pathlib import Path
from typing import Any, Optional

import certifi
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_mcp_adapters.client import MultiServerMCPClient


# =========================================================
# Environment setup
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

WEATHER_SERVER_PATH = BASE_DIR / "custom_weather_mcp_server.py"
UVX_COMMAND = shutil.which("uvx") or "uvx"


def _require_env(name: str, value: Optional[str]) -> str:
    """Return an environment value or raise a readable setup error."""
    if not value or not value.strip():
        raise RuntimeError(
            f"{name} is missing. "
            f"Add {name}=your_key to the project .env file."
        )
    return value.strip()


def _subprocess_env(**updates: Optional[str]) -> dict[str, str]:
    """Preserve the current Windows/Conda environment and add MCP API keys."""
    env = os.environ.copy()
    for key, value in updates.items():
        if value:
            env[key] = value
    return env


def get_groq_llm() -> Optional[ChatGroq]:
    """Returns a ChatGroq LLM instance dynamically based on the current environment."""
    key = os.getenv("GROQ_API_KEY")
    if key and key.strip():
        return ChatGroq(model="llama-3.3-70b-versatile", api_key=key.strip())
    return None


# =========================================================
# Dynamic MCP client factory
# =========================================================

def create_mcp_client() -> MultiServerMCPClient:
    tavily_key = os.getenv("TAVILY_API_KEY", "")
    aviation_key = os.getenv("AVIATION_STACK_API_KEY") or os.getenv("AVIATIONSTACK_API_KEY", "")
    weather_key = os.getenv("OPENWEATHER_API_KEY", "")

    return MultiServerMCPClient(
        {
            "tavily": {
                "transport": "streamable_http",
                "url": f"https://mcp.tavily.com/mcp/?tavilyApiKey={tavily_key}",
            },
            "aviationstack": {
                "transport": "stdio",
                "command": UVX_COMMAND,
                "args": ["aviationstack-mcp"],
                "env": _subprocess_env(AVIATION_STACK_API_KEY=aviation_key),
            },
            "weather": {
                "transport": "stdio",
                "command": sys.executable,
                "args": [str(WEATHER_SERVER_PATH)],
                "env": _subprocess_env(OPENWEATHER_API_KEY=weather_key),
            },
        }
    )


client = create_mcp_client()


async def _get_server_tool(server_name: str, tool_name: str):
    """
    Load one tool from one MCP server dynamically.
    This prevents a broken weather or AviationStack server from crashing an unrelated Tavily request.
    """
    load_dotenv(BASE_DIR / ".env", override=True)

    if server_name == "tavily":
        _require_env("TAVILY_API_KEY", os.getenv("TAVILY_API_KEY"))

    elif server_name == "aviationstack":
        _require_env(
            "AVIATION_STACK_API_KEY",
            os.getenv("AVIATION_STACK_API_KEY") or os.getenv("AVIATIONSTACK_API_KEY"),
        )
        if shutil.which("uvx") is None:
            raise RuntimeError(
                "uvx was not found. Install uv, reopen the terminal, "
                "activate the travel environment, and run `uvx --version`."
            )

    elif server_name == "weather":
        _require_env("OPENWEATHER_API_KEY", os.getenv("OPENWEATHER_API_KEY"))
        if not WEATHER_SERVER_PATH.is_file():
            raise FileNotFoundError(f"Weather MCP server not found: {WEATHER_SERVER_PATH}")

    # Recreate client if keys were updated
    active_client = create_mcp_client()
    tools = await active_client.get_tools(server_name=server_name)

    tool = next((item for item in tools if item.name == tool_name), None)
    if tool is None:
        available_tools = ", ".join(sorted(item.name for item in tools)) or "none"
        raise RuntimeError(
            f"MCP tool '{tool_name}' was not found on server '{server_name}'. "
            f"Available tools: {available_tools}"
        )

    return tool


# =========================================================
# Tavily MCP
# =========================================================

async def tavily_mcp_search(query: str):
    search_tool = await _get_server_tool("tavily", "tavily_search")
    return await search_tool.ainvoke({"query": query})


# =========================================================
# AviationStack MCP
# =========================================================

async def aviation_mcp_call(tool_name: str, tool_args: Optional[dict[str, Any]] = None):
    aviation_tool = await _get_server_tool("aviationstack", tool_name)
    return await aviation_tool.ainvoke(tool_args or {})


# =========================================================
# Weather MCP
# =========================================================

async def weather_mcp_search(city: str):
    weather_tool = await _get_server_tool("weather", "get_current_weather")
    return await weather_tool.ainvoke({"city": city})


async def forecast_mcp_search(city: str):
    forecast_tool = await _get_server_tool("weather", "get_forecast")
    return await forecast_tool.ainvoke({"city": city})


# =========================================================
# Destination Extractor
# =========================================================

async def extract_destination(query: str) -> str:
    active_llm = get_groq_llm()
    if not active_llm:
        raise RuntimeError("GROQ_API_KEY is missing. Add GROQ_API_KEY=your_key to .env file.")

    prompt = f"""
Extract only the destination city or country from the travel request.

Travel request:
{query}

Return only the destination name.
Do not add any explanation.
"""
    response = await active_llm.ainvoke(prompt)
    destination = str(response.content).strip()

    if not destination:
        raise ValueError("The destination could not be extracted.")

    return destination