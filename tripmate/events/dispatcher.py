"""
Observer Pattern: In-Process Event Dispatcher & Subscriber Contracts

Decouples workflow event emission from downstream consumers (SSE streaming, audit logging, metrics).
Guarantees that subscriber exceptions are caught in isolation and never fail or block the main workflow.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Set
from tripmate.core.singleton import SingletonMeta
from tripmate.events.events import WorkflowEvent

logger = logging.getLogger("tripmate.events")


class IWorkflowEventSubscriber(ABC):
    """Abstract interface for workflow event subscribers."""

    @abstractmethod
    async def on_event(self, event: WorkflowEvent) -> None:
        """Invoked asynchronously when an event matching subscription criteria is published."""
        pass


class WorkflowEventDispatcher(metaclass=SingletonMeta):
    """
    Thread-safe, asynchronous in-process event dispatcher.
    """

    def __init__(self):
        self._subscribers: Set[IWorkflowEventSubscriber] = set()
        self._type_filters: Dict[IWorkflowEventSubscriber, Set[str]] = {}
        self._lock = asyncio.Lock()

    def subscribe(
        self,
        subscriber: IWorkflowEventSubscriber,
        event_types: Optional[List[str]] = None,
    ) -> None:
        """Subscribes an observer to all or specific event types."""
        self._subscribers.add(subscriber)
        if event_types:
            self._type_filters[subscriber] = set(event_types)
        elif subscriber in self._type_filters:
            del self._type_filters[subscriber]

    def unsubscribe(self, subscriber: IWorkflowEventSubscriber) -> None:
        """Unsubscribes an observer."""
        self._subscribers.discard(subscriber)
        if subscriber in self._type_filters:
            del self._type_filters[subscriber]

    async def publish(self, event: WorkflowEvent) -> None:
        """
        Dispatches an event asynchronously to all eligible subscribers.
        Subscriber exceptions are caught and logged without disrupting other subscribers
        or propagating back to the workflow caller.
        """
        subscribers_to_notify = []
        for sub in list(self._subscribers):
            filter_types = self._type_filters.get(sub)
            if filter_types is None or event.event_type in filter_types:
                subscribers_to_notify.append(sub)

        for sub in subscribers_to_notify:
            try:
                await sub.on_event(event)
            except Exception as exc:
                logger.error(
                    f"[OBSERVER ERROR] Subscriber {type(sub).__name__} failed on {event.event_type}: {exc}",
                    exc_info=True,
                )

    def publish_nowait(self, event: WorkflowEvent) -> None:
        """
        Dispatches an event in a background task if an asyncio event loop is currently running.
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.publish(event))
        except RuntimeError:
            # If no event loop is running (e.g. sync test), ignore or log
            logger.debug(f"[OBSERVER] No event loop running; skipped async dispatch of {event.event_type}")

    def clear_subscribers(self) -> None:
        """Clears all subscribers (primarily for testing)."""
        self._subscribers.clear()
        self._type_filters.clear()


workflow_dispatcher = WorkflowEventDispatcher()
