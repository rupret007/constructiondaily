from __future__ import annotations

import threading
from typing import Any

from audit.models import AuditEvent


_local = threading.local()


def set_request_audit_context(ip_address: str | None, user_agent: str) -> None:
    _local.ip_address = ip_address
    _local.user_agent = user_agent[:255]


def get_request_audit_context() -> tuple[str | None, str]:
    return getattr(_local, "ip_address", None), getattr(_local, "user_agent", "")


def record_audit_event(
    *,
    actor,
    event_type: str,
    object_type: str = "",
    object_id: str = "",
    project_id: str = "",
    ip_address: str | None = None,
    user_agent: str = "",
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    resolved_ip = ip_address
    resolved_ua = user_agent
    if not resolved_ip and not resolved_ua:
        resolved_ip, resolved_ua = get_request_audit_context()

    return AuditEvent.objects.create(
        actor=actor if actor and actor.is_authenticated else None,
        event_type=event_type,
        object_type=object_type,
        object_id=object_id,
        project_id=project_id,
        ip_address=resolved_ip,
        user_agent=(resolved_ua or "")[:255],
        metadata=metadata or {},
    )
