from __future__ import annotations

from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.middleware.csrf import get_token
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Project, ProjectMembership
from core.serializers import (
    LoginSerializer,
    ProjectMembershipSerializer,
    ProjectSerializer,
    UserSerializer,
)


@api_view(["POST"])
@permission_classes([])
@extend_schema(exclude=True)
def login_view(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.validated_data["user"]
    login(request, user)
    request.session.cycle_key()
    return Response(UserSerializer(user).data)


@api_view(["POST"])
@permission_classes([])
@extend_schema(exclude=True)
def logout_view(request):
    logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([])
@extend_schema(exclude=True)
def session_view(request):
    csrf_token = get_token(request)
    if not request.user.is_authenticated:
        return Response({"authenticated": False, "csrfToken": csrf_token})
    return Response({"authenticated": True, "user": UserSerializer(request.user).data, "csrfToken": csrf_token})


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    queryset = Project.objects.all()
    permission_classes = [IsAuthenticated]
    filterset_fields = ("is_active",)
    ordering_fields = ("name", "code", "created_at")

    def get_queryset(self):
        if self.request.user.is_superuser:
            return self.queryset
        return self.queryset.filter(memberships__user=self.request.user, memberships__is_active=True).distinct()

    def _ensure_admin_access(self, project_id: str):
        if self.request.user.is_superuser:
            return
        allowed = ProjectMembership.objects.filter(
            user=self.request.user,
            project_id=project_id,
            role=ProjectMembership.Role.ADMIN,
            is_active=True,
        ).exists()
        if not allowed:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Admin role is required.")

    def perform_create(self, serializer):
        project = serializer.save()
        ProjectMembership.objects.get_or_create(
            user=self.request.user,
            project=project,
            role=ProjectMembership.Role.ADMIN,
            defaults={"is_active": True},
        )

    def perform_update(self, serializer):
        project = self.get_object()
        self._ensure_admin_access(str(project.id))
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_admin_access(str(instance.id))
        instance.delete()


class ProjectMembershipViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ProjectMembershipSerializer
    queryset = ProjectMembership.objects.select_related("user", "project")
    permission_classes = [IsAuthenticated]
    filterset_fields = ("project", "role", "is_active")
    ordering_fields = ("created_at", "updated_at")

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return self.queryset
        project_ids = ProjectMembership.objects.filter(
            user=user,
            role__in=[ProjectMembership.Role.ADMIN, ProjectMembership.Role.PROJECT_MANAGER],
            is_active=True,
        ).values_list("project_id", flat=True)
        return self.queryset.filter(project_id__in=project_ids)

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        if not ProjectMembership.objects.filter(
            user=self.request.user,
            project=project,
            role__in=[ProjectMembership.Role.ADMIN, ProjectMembership.Role.PROJECT_MANAGER],
            is_active=True,
        ).exists():
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Admin or Project Manager role is required.")
        serializer.save()


class UserDirectoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    List/search users. Intentionally available to any authenticated user (e.g. for assignment,
    mentions). To restrict to project members only, filter queryset by users who share a project
    with request.user.
    """
    serializer_class = UserSerializer
    queryset = User.objects.all()
    permission_classes = [IsAuthenticated]
    ordering_fields = ("username", "first_name", "last_name")

    def get_queryset(self):
        query = self.request.query_params.get("query")
        if not query:
            return self.queryset.order_by("username")[:50]
        return self.queryset.filter(
            Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query)
        ).order_by("username")[:50]
