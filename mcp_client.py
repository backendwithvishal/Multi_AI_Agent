"""
MultiServerMCPClient Connection Manager

This module manages connections to all Model Context Protocol (MCP) servers:
1. Tavily MCP Server (HTTP Streamable transport for live web hotel searches).
2. AviationStack MCP Server (stdio transport for live flight status and airport data).
3. Custom Weather FastMCP Server (stdio transport for OpenWeather current & forecast metrics).
"""

import asyncio
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import certifi
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger("tripmate.mcp_client")


# =========================================================
# Environment setup
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

WEATHER_SERVER_PATH = BASE_DIR / "custom_weather_mcp_server.py"

def _find_uvx() -> str:
    uvx_path = shutil.which("uvx")
    if uvx_path:
        return uvx_path
    venv_bin_uvx = Path(sys.prefix) / "bin" / ("uvx.exe" if sys.platform == "win32" else "uvx")
    if venv_bin_uvx.exists():
        return str(venv_bin_uvx)
    venv_scripts_uvx = Path(sys.prefix) / "Scripts" / "uvx.exe"
    if venv_scripts_uvx.exists():
        return str(venv_scripts_uvx)
    return "uvx"

UVX_COMMAND = _find_uvx()


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


class MCPManager:
    """Manages persistent MCP server connections and lifecycle without re-spawning per request."""

    def __init__(self):
        self._client: Optional[MultiServerMCPClient] = None
        self._tools: Dict[Tuple[str, str], Any] = {}
        self._lock = asyncio.Lock()
        self._failures: Dict[str, int] = {}
        self._last_failure_time: Dict[str, float] = {}

    def get_client(self) -> MultiServerMCPClient:
        if self._client is None:
            self._client = create_mcp_client()
        return self._client

    async def get_tool(self, server_name: str, tool_name: str):
        key = (server_name, tool_name)
        if key in self._tools:
            return self._tools[key]

        async with self._lock:
            if key in self._tools:
                return self._tools[key]

            now = time.time()
            fail_count = self._failures.get(server_name, 0)
            if fail_count > 0:
                last_fail = self._last_failure_time.get(server_name, 0)
                backoff_wait = min(15.0, 0.5 * (2 ** (fail_count - 1)))
                if now - last_fail < backoff_wait:
                    raise RuntimeError(
                        f"MCP server '{server_name}' temporarily in backoff cooldown ({backoff_wait:.1f}s) after failure."
                    )

            load_dotenv(BASE_DIR / ".env", override=False)
            if server_name == "tavily":
                _require_env("TAVILY_API_KEY", os.getenv("TAVILY_API_KEY"))
            elif server_name == "aviationstack":
                _require_env(
                    "AVIATION_STACK_API_KEY",
                    os.getenv("AVIATION_STACK_API_KEY") or os.getenv("AVIATIONSTACK_API_KEY"),
                )
            elif server_name == "weather":
                _require_env("OPENWEATHER_API_KEY", os.getenv("OPENWEATHER_API_KEY"))

            client = self.get_client()
            try:
                tools = await client.get_tools(server_name=server_name)
                for t in tools:
                    self._tools[(server_name, t.name)] = t
                self._failures[server_name] = 0
            except Exception as exc:
                self._failures[server_name] = fail_count + 1
                self._last_failure_time[server_name] = now
                logger.warning(
                    f"[MCPManager] Failed to load tools from '{server_name}': {exc}. Failure count: {self._failures[server_name]}"
                )
                self._client = None
                raise

            tool = self._tools.get(key)
            if tool is None:
                available = ", ".join(sorted(t.name for (s, _), t in self._tools.items() if s == server_name)) or "none"
                raise RuntimeError(
                    f"MCP tool '{tool_name}' was not found on server '{server_name}'. Available: {available}"
                )
            return tool

    async def startup(self):
        """Initializes client and pre-warms connections."""
        async with self._lock:
            if self._client is None:
                self._client = create_mcp_client()
            logger.info("[MCPManager] MCP Client Manager started.")

    async def shutdown(self):
        """Cleanly releases MCP subprocesses and clears tool references."""
        async with self._lock:
            self._tools.clear()
            self._client = None
            logger.info("[MCPManager] MCP Client Manager stopped cleanly.")


mcp_manager = MCPManager()
client = mcp_manager.get_client()


async def _get_server_tool(server_name: str, tool_name: str):
    """Load tool from managed persistent MCP client without spawning per request."""
    return await mcp_manager.get_tool(server_name, tool_name)


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
    """Extracts target destination using configured LLM or fallback heuristics."""
    from tripmate.services.model_router import model_router, ModelTier

    active_llm = model_router.get_model(ModelTier.FAST) or get_groq_llm()
    if active_llm:
        prompt = f"""
Extract only the destination city or country from the travel request.

Travel request:
{query}

Return only the destination name.
Do not add any explanation.
"""
        try:
            response = await active_llm.ainvoke(prompt)
            destination = str(response.content).strip()
            if destination:
                return destination
        except Exception:
            pass

    # Heuristic fallback if LLM is unavailable or failed
    words = query.strip().split()
    for trigger in ["to", "in", "for", "visit", "visiting"]:
        if trigger in words:
            idx = words.index(trigger)
            if idx + 1 < len(words):
                return words[idx + 1].strip(".,!?;:\"'")

    return "Destination"