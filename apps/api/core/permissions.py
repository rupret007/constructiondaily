from __future__ import annotations

from typing import Iterable

from rest_framework.permissions import BasePermission

from core.models import ProjectMembership


def user_has_project_role(user, project_id: str, roles: Iterable[str]) -> bool:
    if not user or not user.is_authenticated:
        return False
    return ProjectMembership.objects.filter(
        user=user,
        project_id=project_id,
        role__in=list(roles),
        is_active=True,
    ).exists()


class IsProjectMember(BasePermission):
    def has_permission(self, request, view):
        project_id = request.query_params.get("project") or request.data.get("project")
        if not project_id:
            return request.user and request.user.is_authenticated
        return user_has_project_role(
            request.user,
            project_id,
            (
                ProjectMembership.Role.FOREMAN,
                ProjectMembership.Role.SUPERINTENDENT,
                ProjectMembership.Role.PROJECT_MANAGER,
                ProjectMembership.Role.SAFETY,
                ProjectMembership.Role.ADMIN,
            ),
        )
