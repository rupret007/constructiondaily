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


def record_field_changes(
    *,
    actor,
    instance,
    old_values: dict[str, Any],
    new_values: dict[str, Any],
    project_id: str = "",
):
    changes = {}
    for field, new_val in new_values.items():
        old_val = old_values.get(field)
        if str(old_val) != str(new_val):
            changes[field] = {"old": old_val, "new": new_val}

    if changes:
        record_audit_event(
            actor=actor,
            event_type="object.fields_changed",
            object_type=instance.__class__.__name__,
            object_id=str(instance.pk),
            project_id=project_id or (str(instance.project_id) if hasattr(instance, "project_id") else ""),
            metadata={"changes": changes},
        )
