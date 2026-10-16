"""
CQRS Pattern: In-Process Command & Query Buses

Provides unified dispatchers for routing commands and queries to their respective handlers.
"""

from typing import Any, Callable, Dict, Type
from tripmate.core.singleton import SingletonMeta


class CommandBus(metaclass=SingletonMeta):
    """Dispatches commands to their registered handler."""

    def __init__(self):
        self._handlers: Dict[Type[Any], Callable[[Any], Any]] = {}

    def register(self, command_type: Type[Any], handler: Callable[[Any], Any]) -> None:
        self._handlers[command_type] = handler

    def execute(self, command: Any) -> Any:
        handler = self._handlers.get(type(command))
        if not handler:
            raise ValueError(f"No handler registered for command '{type(command).__name__}'")
        return handler(command)


class QueryBus(metaclass=SingletonMeta):
    """Dispatches read queries to their registered handler."""

    def __init__(self):
        self._handlers: Dict[Type[Any], Callable[[Any], Any]] = {}

    def register(self, query_type: Type[Any], handler: Callable[[Any], Any]) -> None:
        self._handlers[query_type] = handler

    def execute(self, query: Any) -> Any:
        handler = self._handlers.get(type(query))
        if not handler:
            raise ValueError(f"No handler registered for query '{type(query).__name__}'")
        return handler(query)


command_bus = CommandBus()
query_bus = QueryBus()
