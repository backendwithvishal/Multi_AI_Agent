"""
Dynamic Agent Registry Module

This module provides a centralized registry for all specialist, supervisor, planner, and critic agents.
Agents expose standardized metadata:
- Name, description, capabilities
- Required MCP tools
- Risk level (low, medium, high)
- Input & output schemas
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Type
from pydantic import BaseModel

from tripmate.schemas.agents import StructuredAgentOutput


class AgentMetadata(BaseModel):
    """Declarative metadata describing an agent's capabilities and operational parameters."""
    name: str
    description: str
    capabilities: List[str] = []
    required_tools: List[str] = []
    risk_level: str = "low"
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None


class BaseAgent(ABC):
    """Abstract base class for all platform agents."""

    def __init__(self, metadata: AgentMetadata):
        self.metadata = metadata

    @property
    def name(self) -> str:
        return self.metadata.name

    @abstractmethod
    async def run(self, llm: Any, query: str, context: Optional[Dict[str, Any]] = None) -> StructuredAgentOutput:
        """Executes agent logic and returns structured output."""
        pass


class AgentRegistry:
    """Thread-safe registry for agent discovery and dynamic instantiation."""

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """Registers an agent instance."""
        self._agents[agent.name] = agent

    def get(self, name: str) -> Optional[BaseAgent]:
        """Retrieves an agent by name."""
        return self._agents.get(name)

    def list_agents(self) -> List[AgentMetadata]:
        """Returns metadata for all registered agents."""
        return [agent.metadata for agent in self._agents.values()]

    def get_all(self) -> Dict[str, BaseAgent]:
        """Returns map of all registered agents."""
        return self._agents.copy()


# Shared global singleton registry
agent_registry = AgentRegistry()
