"""
Agent Factory Pattern

Centralizes the discovery, validation, and dynamic instantiation of specialist and orchestration agents.
"""

from typing import Any, Dict, List, Type
from tripmate.agents.registry import BaseAgent, AgentRegistry, agent_registry


class AgentFactory:
    """
    Factory for instantiating and configuring domain-specific travel agents.
    Validates agent types and prevents accidental duplicate or invalid configurations.
    """

    _registry_map: Dict[str, Type[BaseAgent]] = {}

    @classmethod
    def register_agent_class(cls, agent_name: str, agent_cls: Type[BaseAgent]) -> None:
        """Registers an agent class with the factory."""
        cls._registry_map[agent_name] = agent_cls

    @classmethod
    def create_agent(cls, agent_name: str, **kwargs: Any) -> BaseAgent:
        """
        Creates and returns a new agent instance.
        Fails with clear ValueError if the requested agent type is unsupported.
        """
        # Lazy load specialist classes if not yet registered
        if not cls._registry_map:
            cls._ensure_defaults_registered()

        agent_cls = cls._registry_map.get(agent_name)
        if not agent_cls:
            available = list(cls._registry_map.keys())
            raise ValueError(
                f"Unsupported agent type '{agent_name}'. Registered agent types: {available}"
            )
        return agent_cls(**kwargs)

    @classmethod
    def create_and_register_all(cls, registry: AgentRegistry = agent_registry) -> Dict[str, BaseAgent]:
        """
        Instantiates all default specialist agents and registers them into the agent registry.
        """
        cls._ensure_defaults_registered()
        instances: Dict[str, BaseAgent] = {}
        for name in cls._registry_map:
            instance = cls.create_agent(name)
            registry.register(instance)
            instances[name] = instance
        return instances

    @classmethod
    def list_supported_agents(cls) -> List[str]:
        cls._ensure_defaults_registered()
        return list(cls._registry_map.keys())

    @classmethod
    def _ensure_defaults_registered(cls) -> None:
        if not cls._registry_map:
            from tripmate.agents.specialists import (
                FlightAgent,
                HotelAgent,
                WeatherAgent,
                BudgetAgent,
                ItineraryAgent,
            )
            cls._registry_map["flight_agent"] = FlightAgent
            cls._registry_map["hotel_agent"] = HotelAgent
            cls._registry_map["weather_agent"] = WeatherAgent
            cls._registry_map["budget_agent"] = BudgetAgent
            cls._registry_map["itinerary_agent"] = ItineraryAgent
