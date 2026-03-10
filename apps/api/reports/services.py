from __future__ import annotations

import hashlib
import json
from typing import Any

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from audit.services import record_audit_event
from core.models import ProjectMembership
from core.permissions import user_has_project_role
from reports.models import ApprovalAction, DailyReport, ReportSnapshot
from reports.pdf import save_report_snapshot


def _report_hash_payload(report: DailyReport) -> str:
    payload = {
        "report_id": str(report.id),
        "project_id": str(report.project_id),
        "date": str(report.report_date),
        "status": report.status,
        "summary": report.summary,
        "revision": report.revision,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def transition_report(
    report: DailyReport,
    action: str,
    actor,
    ip_address: str | None,
    user_agent: str,
    reason: str = "",
    signature_intent: str = "",
):
    reason = (reason or "").strip()
    role_lookup = {
        "submit": (ProjectMembership.Role.FOREMAN, ProjectMembership.Role.SUPERINTENDENT, ProjectMembership.Role.ADMIN),
        "review": (ProjectMembership.Role.PROJECT_MANAGER, ProjectMembership.Role.ADMIN),
        "reject": (ProjectMembership.Role.PROJECT_MANAGER, ProjectMembership.Role.ADMIN),
        "approve": (ProjectMembership.Role.PROJECT_MANAGER, ProjectMembership.Role.ADMIN),
        "lock": (ProjectMembership.Role.ADMIN,),
        "sign": (ProjectMembership.Role.PROJECT_MANAGER, ProjectMembership.Role.ADMIN),
    }
    allowed_roles = role_lookup.get(action)
    if not allowed_roles:
        raise ValidationError("Invalid transition action.")
    if action == "reject" and not reason:
        raise ValidationError("Rejection reason is required.")
    if not user_has_project_role(actor, str(report.project_id), allowed_roles):
        raise PermissionDenied("You do not have permission to perform this action.")
    if report.status == DailyReport.Status.LOCKED and action != "sign":
        raise ValidationError("Locked reports cannot be transitioned.")

    expected = {
        "submit": {DailyReport.Status.DRAFT},
        "review": {DailyReport.Status.SUBMITTED},
        "reject": {DailyReport.Status.SUBMITTED, DailyReport.Status.REVIEWED},
        "approve": {DailyReport.Status.REVIEWED},
        "lock": {DailyReport.Status.APPROVED},
        "sign": {DailyReport.Status.APPROVED},
    }
    if report.status not in expected[action]:
        raise ValidationError(f"Cannot {action} report while in '{report.status}'.")

    with transaction.atomic():
        report = DailyReport.objects.select_for_update().get(pk=report.pk)
        if report.status == DailyReport.Status.LOCKED and action != "sign":
            raise ValidationError("Locked reports cannot be transitioned.")
        if report.status not in expected[action]:
            raise ValidationError(f"Cannot {action} report while in '{report.status}'.")
        if action == "submit":
            report.status = DailyReport.Status.SUBMITTED
            report.rejection_reason = ""
        elif action == "review":
            report.status = DailyReport.Status.REVIEWED
        elif action == "reject":
            report.status = DailyReport.Status.DRAFT
            report.rejection_reason = reason
        elif action in {"approve", "sign"}:
            report.status = DailyReport.Status.APPROVED
        elif action == "lock":
            report.status = DailyReport.Status.LOCKED
            report.locked_at = timezone.now()
            report.locked_by = actor

        report.revision += 1
        report.save(update_fields=["status", "rejection_reason", "locked_at", "locked_by", "revision", "updated_at"])

        persisted_signature_intent = ""
        if action in {"approve", "sign"}:
            persisted_signature_intent = (signature_intent or "").strip() or "I acknowledge and approve this report."

        approval_action = ApprovalAction.objects.create(
            report=report,
            actor=actor,
            action=ApprovalAction.Action(action),
            reason=reason,
            document_hash=_report_hash_payload(report),
            actor_ip=ip_address,
            actor_user_agent=user_agent[:255],
            signature_intent=persisted_signature_intent,
        )

        snapshot_path = ""
        snapshot_sha = ""
        if action in {"approve", "sign", "lock"}:
            snapshot_path, snapshot_sha = save_report_snapshot(report)
            ReportSnapshot.objects.update_or_create(
                report=report,
                revision=report.revision,
                defaults={"file_path": snapshot_path, "sha256": snapshot_sha},
            )

        record_audit_event(
            actor=actor,
            event_type=f"report.{action}",
            object_type="DailyReport",
            object_id=str(report.id),
            project_id=str(report.project_id),
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={
                "status": report.status,
                "reason": reason,
                "approval_action_id": str(approval_action.id),
                "snapshot_path": snapshot_path,
                "snapshot_sha256": snapshot_sha,
            },
        )

    return report
