from __future__ import annotations

from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated

from core.models import ProjectMembership
from core.permissions import user_has_project_role
from reports.models import DailyReport
from reports.services import bump_report_revision
from safety.models import SafetyEntry
from safety.serializers import SafetyEntrySerializer


class SafetyEntryViewSet(viewsets.ModelViewSet):
    serializer_class = SafetyEntrySerializer
    queryset = SafetyEntry.objects.select_related("report", "report__project")
    permission_classes = [IsAuthenticated]
    filterset_fields = ("report", "entry_type", "severity", "closed")
    ordering_fields = ("created_at", "updated_at")

    def get_queryset(self):
        projects = ProjectMembership.objects.filter(user=self.request.user, is_active=True).values_list(
            "project_id", flat=True
        )
        return self.queryset.filter(report__project_id__in=projects)

    def perform_create(self, serializer):
        report = serializer.validated_data["report"]
        _ensure_report_is_draft(report, "add")
        if not user_has_project_role(
            self.request.user,
            str(report.project_id),
            (
                ProjectMembership.Role.SAFETY,
                ProjectMembership.Role.SUPERINTENDENT,
                ProjectMembership.Role.ADMIN,
            ),
        ):
            raise PermissionDenied("Insufficient permissions.")
        serializer.save()
        bump_report_revision(report)

    def perform_update(self, serializer):
        report = serializer.instance.report
        incoming_report = serializer.validated_data.get("report", report)
        if incoming_report.id != report.id:
            raise ValidationError("Report cannot be changed after entry creation.")
        _ensure_report_is_draft(report, "edit")
        if not user_has_project_role(
            self.request.user,
            str(report.project_id),
            (
                ProjectMembership.Role.SAFETY,
                ProjectMembership.Role.SUPERINTENDENT,
                ProjectMembership.Role.ADMIN,
            ),
        ):
            raise PermissionDenied("Insufficient permissions.")
        serializer.save()
        bump_report_revision(report)

    def perform_destroy(self, instance):
        _ensure_report_is_draft(instance.report, "delete")
        if not user_has_project_role(
            self.request.user,
            str(instance.report.project_id),
            (
                ProjectMembership.Role.SAFETY,
                ProjectMembership.Role.SUPERINTENDENT,
                ProjectMembership.Role.ADMIN,
            ),
        ):
            raise PermissionDenied("Insufficient permissions.")
        report = instance.report
        instance.delete()
        bump_report_revision(report)


def _ensure_report_is_draft(report: DailyReport, action: str):
    if report.status != DailyReport.Status.DRAFT:
        raise ValidationError(f"Cannot {action} safety entry unless report is draft.")
