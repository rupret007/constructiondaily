from __future__ import annotations

from rest_framework.permissions import BasePermission, SAFE_METHODS

from core.models import ProjectMembership
from core.permissions import user_has_project_role
from reports.models import DailyReport


class CanAccessReport(BasePermission):
    def has_object_permission(self, request, view, obj: DailyReport):
        return user_has_project_role(
            request.user,
            str(obj.project_id),
            (
                ProjectMembership.Role.FOREMAN,
                ProjectMembership.Role.SUPERINTENDENT,
                ProjectMembership.Role.PROJECT_MANAGER,
                ProjectMembership.Role.SAFETY,
                ProjectMembership.Role.ADMIN,
            ),
        )


class CanEditReport(BasePermission):
    def has_object_permission(self, request, view, obj: DailyReport):
        if request.method in SAFE_METHODS:
            return True
        if obj.status == DailyReport.Status.LOCKED:
            return False
        return user_has_project_role(
            request.user,
            str(obj.project_id),
            (
                ProjectMembership.Role.FOREMAN,
                ProjectMembership.Role.SUPERINTENDENT,
                ProjectMembership.Role.ADMIN,
            ),
        )


class CanApproveReport(BasePermission):
    def has_object_permission(self, request, view, obj: DailyReport):
        return user_has_project_role(
            request.user,
            str(obj.project_id),
            (
                ProjectMembership.Role.PROJECT_MANAGER,
                ProjectMembership.Role.ADMIN,
            ),
        )
