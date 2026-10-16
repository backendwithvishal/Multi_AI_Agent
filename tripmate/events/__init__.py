"""
Observer Pattern Module

Exposes events, dispatchers, and subscribers.
"""

from tripmate.events.events import (
    ApprovalRequiredEvent,
    CriticCompletedEvent,
    ItineraryCompletedEvent,
    SpecialistsCompletedEvent,
    SupervisorCompletedEvent,
    WorkflowCompletedEvent,
    WorkflowEvent,
    WorkflowFailedEvent,
    WorkflowStartedEvent,
)
from tripmate.events.dispatcher import (
    IWorkflowEventSubscriber,
    WorkflowEventDispatcher,
    workflow_dispatcher,
)
from tripmate.events.subscribers import (
    AuditLogSubscriber,
    MetricsCollectorSubscriber,
    SSEEventBridgeSubscriber,
)

__all__ = [
    "WorkflowEvent",
    "WorkflowStartedEvent",
    "SupervisorCompletedEvent",
    "SpecialistsCompletedEvent",
    "CriticCompletedEvent",
    "ItineraryCompletedEvent",
    "ApprovalRequiredEvent",
    "WorkflowCompletedEvent",
    "WorkflowFailedEvent",
    "IWorkflowEventSubscriber",
    "WorkflowEventDispatcher",
    "workflow_dispatcher",
    "AuditLogSubscriber",
    "MetricsCollectorSubscriber",
    "SSEEventBridgeSubscriber",
]
