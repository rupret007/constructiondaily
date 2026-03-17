from __future__ import annotations

from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from audit.models import AuditEvent
from audit.serializers import AuditEventSerializer
from core.models import ProjectMembership


class AuditEventViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = AuditEventSerializer
    queryset = AuditEvent.objects.select_related("actor")
    permission_classes = [IsAuthenticated]
    filterset_fields = ("project_id", "event_type", "object_type")
    ordering_fields = ("created_at",)

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return self.queryset

        allowed_projects = list(
            ProjectMembership.objects.filter(
                user=user,
                role__in=[ProjectMembership.Role.ADMIN, ProjectMembership.Role.PROJECT_MANAGER],
                is_active=True,
            ).values_list("project_id", flat=True)
        )
        return self.queryset.filter(project_id__in=[str(pid) for pid in allowed_projects])
