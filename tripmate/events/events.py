"""
Observer Pattern: Domain Event Definitions

Defines strongly-typed event objects emitted during multi-agent workflow execution.
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class WorkflowEvent:
    """Base class for all in-process workflow events."""
    thread_id: str
    run_id: str
    event_type: str = "workflow.event"
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:10]}")
    timestamp: float = field(default_factory=time.time)
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowStartedEvent(WorkflowEvent):
    request_id: str = ""
    event_type: str = "workflow.started"


@dataclass
class SupervisorCompletedEvent(WorkflowEvent):
    selected_agents: List[str] = field(default_factory=list)
    reasoning: str = ""
    event_type: str = "supervisor.completed"


@dataclass
class SpecialistsCompletedEvent(WorkflowEvent):
    node_name: str = "parallel_specialists"
    event_type: str = "specialists.completed"


@dataclass
class CriticCompletedEvent(WorkflowEvent):
    critic_report: Optional[Dict[str, Any]] = None
    event_type: str = "critic.completed"


@dataclass
class ItineraryCompletedEvent(WorkflowEvent):
    status_msg: str = "draft_synthesized"
    event_type: str = "itinerary.completed"


@dataclass
class ApprovalRequiredEvent(WorkflowEvent):
    approval_request: str = ""
    event_type: str = "approval.required"


@dataclass
class WorkflowCompletedEvent(WorkflowEvent):
    success: bool = True
    request_id: str = ""
    result: Dict[str, Any] = field(default_factory=dict)
    event_type: str = "workflow.completed"


@dataclass
class WorkflowFailedEvent(WorkflowEvent):
    error: str = ""
    request_id: str = ""
    event_type: str = "workflow.failed"
