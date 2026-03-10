from __future__ import annotations

from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated

from core.models import ProjectMembership
from core.permissions import user_has_project_role
from reports.models import DailyReport
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
        if report.status == DailyReport.Status.LOCKED:
            raise ValidationError("Cannot add safety entry to locked report.")
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

    def perform_update(self, serializer):
        report = serializer.instance.report
        if report.status == DailyReport.Status.LOCKED:
            raise ValidationError("Cannot edit safety entry in locked report.")
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

    def perform_destroy(self, instance):
        if instance.report.status == DailyReport.Status.LOCKED:
            raise ValidationError("Cannot delete safety entry in locked report.")
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
        instance.delete()
