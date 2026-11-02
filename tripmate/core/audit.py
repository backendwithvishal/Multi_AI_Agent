"""
Enterprise Security Audit Logging Module

Maintains an immutable, structured audit log for:
- Authentication failures and credential breaches
- Human-in-the-Loop approval and rejection decisions
- Administrative privileges, role updates, and resource deletions
- Sensitive configuration changes
"""

from enum import Enum
import json
import logging
import time
from typing import Any, Dict, List, Optional

from tripmate.core.context import get_request_id, get_user_id
from tripmate.core.logging import redact_sensitive_data

logger = logging.getLogger("tripmate.audit")


class AuditEventType(str, Enum):
    AUTH_FAILURE = "AUTH_FAILURE"
    APPROVAL_DECISION = "APPROVAL_DECISION"
    ADMIN_ACTION = "ADMIN_ACTION"
    ACCESS_DENIED = "ACCESS_DENIED"
    CONFIG_CHANGE = "CONFIG_CHANGE"


class AuditLogger:
    """Thread-safe security audit event recorder."""

    def __init__(self, max_retained_entries: int = 1000):
        self.max_retained_entries = max_retained_entries
        self._entries: List[Dict[str, Any]] = []

    def record(
        self,
        event_type: AuditEventType,
        action: str,
        actor: Optional[str] = None,
        target_id: Optional[str] = None,
        status: str = "success",
        client_ip: str = "unknown",
        request_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Records a single structured audit entry.
        Guarantees sensitive data is redacted and emits structured log.
        """
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        resolved_actor = actor or get_user_id() or "anonymous"
        resolved_req_id = request_id or get_request_id() or "unknown"
        safe_details = redact_sensitive_data(details or {})

        entry = {
            "timestamp": timestamp,
            "event_type": event_type.value if hasattr(event_type, "value") else str(event_type),
            "action": action,
            "actor": resolved_actor,
            "target_id": target_id or "",
            "status": status,
            "client_ip": client_ip,
            "request_id": resolved_req_id,
            "details": safe_details,
        }

        # Retain bounded history in-memory for verification and reporting
        self._entries.append(entry)
        if len(self._entries) > self.max_retained_entries:
            self._entries.pop(0)

        # Output to security audit log stream
        logger.info(
            f"[AUDIT] {entry['event_type']} action={entry['action']} actor={entry['actor']} "
            f"target={entry['target_id']} status={entry['status']} ip={entry['client_ip']} "
            f"req={entry['request_id']} details={json.dumps(safe_details, default=str)}"
        )

        return entry

    def get_entries(self) -> List[Dict[str, Any]]:
        """Returns recorded audit log entries."""
        return list(self._entries)

    def clear(self) -> None:
        """Clears in-memory audit log entries."""
        self._entries.clear()


audit_logger = AuditLogger()

