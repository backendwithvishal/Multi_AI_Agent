"""
Observer Pattern: Concrete Subscribers

Provides decoupled event listeners for:
1. `AuditLogSubscriber`: Logs structured operational telemetry.
2. `MetricsCollectorSubscriber`: Updates Prometheus metrics on agent/workflow milestones.
3. `SSEEventBridgeSubscriber`: Feeds live Server-Sent Events queues without coupling service logic to HTTP streaming formats.
"""

import asyncio
import json
import logging
from typing import Optional
from tripmate.events.dispatcher import IWorkflowEventSubscriber
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

logger = logging.getLogger("tripmate.observers")


class AuditLogSubscriber(IWorkflowEventSubscriber):
    """Subscribes to workflow events and produces structured audit log records."""

    async def on_event(self, event: WorkflowEvent) -> None:
        logger.info(
            f"[AUDIT EVENT] type={event.event_type} thread_id={event.thread_id} run_id={event.run_id}"
        )


class MetricsCollectorSubscriber(IWorkflowEventSubscriber):
    """Subscribes to workflow events and records Prometheus counters/histograms."""

    async def on_event(self, event: WorkflowEvent) -> None:
        try:
            from tripmate.middleware.metrics import metrics_registry
            if isinstance(event, WorkflowCompletedEvent):
                metrics_registry.record_agent_execution("workflow", "success", 0.0)
            elif isinstance(event, WorkflowFailedEvent):
                metrics_registry.record_agent_execution("workflow", "failure", 0.0)
            elif isinstance(event, SupervisorCompletedEvent):
                metrics_registry.record_agent_execution("supervisor", "completed", 0.0)
        except Exception as exc:
            logger.debug(f"MetricsCollectorSubscriber notice: {exc}")


class SSEEventBridgeSubscriber(IWorkflowEventSubscriber):
    """
    Subscribes to workflow events and formats them as SSE messages queued into an asyncio.Queue.
    Allows clean decoupling between workflow execution and HTTP Server-Sent Event streaming.
    """

    def __init__(self, queue: asyncio.Queue):
        self.queue = queue

    async def on_event(self, event: WorkflowEvent) -> None:
        sse_text = ""
        if isinstance(event, WorkflowStartedEvent):
            data = {"thread_id": event.thread_id, "request_id": event.request_id, "status": "started"}
            sse_text = f"event: workflow.started\ndata: {json.dumps(data)}\n\n"
        elif isinstance(event, SupervisorCompletedEvent):
            data = {"selected_agents": event.selected_agents, "reasoning": event.reasoning}
            sse_text = f"event: supervisor.completed\ndata: {json.dumps(data)}\n\n"
        elif isinstance(event, SpecialistsCompletedEvent):
            data = {"status": "completed", "node": event.node_name}
            sse_text = f"event: specialists.completed\ndata: {json.dumps(data)}\n\n"
        elif isinstance(event, CriticCompletedEvent):
            data = {"critic_report": event.critic_report}
            sse_text = f"event: critic.completed\ndata: {json.dumps(data)}\n\n"
        elif isinstance(event, ItineraryCompletedEvent):
            data = {"status": event.status_msg}
            sse_text = f"event: itinerary.completed\ndata: {json.dumps(data)}\n\n"
        elif isinstance(event, ApprovalRequiredEvent):
            data = {"approval_request": event.approval_request}
            sse_text = f"event: approval.required\ndata: {json.dumps(data)}\n\n"
        elif isinstance(event, WorkflowCompletedEvent):
            data = {"success": True, "request_id": event.request_id, **event.result}
            sse_text = f"event: workflow.completed\ndata: {json.dumps(data)}\n\n"
        elif isinstance(event, WorkflowFailedEvent):
            data = {"success": False, "error": event.error, "request_id": event.request_id}
            sse_text = f"event: workflow.failed\ndata: {json.dumps(data)}\n\n"

        if sse_text:
            await self.queue.put(sse_text)
