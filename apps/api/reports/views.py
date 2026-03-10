from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import urlopen

from django.db import transaction
from django.http import HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from audit.services import get_request_audit_context, record_audit_event
from core.models import ProjectMembership
from core.permissions import user_has_project_role
from reports.models import DailyReport, DelayEntry, EquipmentEntry, LaborEntry, MaterialEntry, WorkLogEntry
from reports.pdf import build_report_pdf
from reports.serializers import (
    DailyReportDetailSerializer,
    DelayEntrySerializer,
    EquipmentEntrySerializer,
    LaborEntrySerializer,
    MaterialEntrySerializer,
    ReportSummarySerializer,
    ReportTransitionSerializer,
    WorkLogEntrySerializer,
)
from reports.services import transition_report


class DailyReportViewSet(viewsets.ModelViewSet):
    serializer_class = ReportSummarySerializer
    queryset = DailyReport.objects.select_related("project", "prepared_by", "locked_by")
    permission_classes = [IsAuthenticated]
    filterset_fields = ("project", "status", "report_date")
    ordering_fields = ("report_date", "created_at")

    def get_queryset(self):
        memberships = ProjectMembership.objects.filter(user=self.request.user, is_active=True).values_list(
            "project_id", flat=True
        )
        return self.queryset.filter(project_id__in=memberships)

    def get_serializer_class(self):
        if self.action == "retrieve":
            return DailyReportDetailSerializer
        return super().get_serializer_class()

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        if not user_has_project_role(
            self.request.user,
            str(project.id),
            (
                ProjectMembership.Role.FOREMAN,
                ProjectMembership.Role.SUPERINTENDENT,
                ProjectMembership.Role.PROJECT_MANAGER,
                ProjectMembership.Role.ADMIN,
            ),
        ):
            raise PermissionDenied("Insufficient permissions.")
        report = serializer.save(prepared_by=self.request.user)
        record_audit_event(
            actor=self.request.user,
            event_type="report.created",
            object_type="DailyReport",
            object_id=str(report.id),
            project_id=str(report.project_id),
            metadata={"status": report.status},
        )

    def perform_update(self, serializer):
        with transaction.atomic():
            report = DailyReport.objects.select_for_update().get(pk=serializer.instance.pk)
            if report.status == DailyReport.Status.LOCKED:
                raise PermissionDenied("Locked reports cannot be edited.")
            incoming_revision = self.request.data.get("revision")
            if incoming_revision is not None:
                try:
                    parsed_revision = int(incoming_revision)
                except (TypeError, ValueError) as exc:
                    raise ValidationError("Revision must be numeric.") from exc
                if parsed_revision != report.revision:
                    raise ValidationError("Report has changed. Refresh and manually resolve conflicts.")
            if not user_has_project_role(
                self.request.user,
                str(report.project_id),
                (
                    ProjectMembership.Role.FOREMAN,
                    ProjectMembership.Role.SUPERINTENDENT,
                    ProjectMembership.Role.ADMIN,
                ),
            ):
                raise PermissionDenied("Insufficient permissions.")
            updated = serializer.save()
            record_audit_event(
                actor=self.request.user,
                event_type="report.updated",
                object_type="DailyReport",
                object_id=str(updated.id),
                project_id=str(updated.project_id),
                metadata={"status": updated.status},
            )

    def perform_destroy(self, instance):
        if instance.status != DailyReport.Status.DRAFT:
            raise PermissionDenied("Only draft reports can be deleted.")
        if not user_has_project_role(
            self.request.user,
            str(instance.project_id),
            (
                ProjectMembership.Role.SUPERINTENDENT,
                ProjectMembership.Role.ADMIN,
            ),
        ):
            raise PermissionDenied("Insufficient permissions.")
        project_id = str(instance.project_id)
        report_id = str(instance.id)
        instance.delete()
        record_audit_event(
            actor=self.request.user,
            event_type="report.deleted",
            object_type="DailyReport",
            object_id=report_id,
            project_id=project_id,
            metadata={"report_id": report_id},
        )

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, pk=None):
        return self._transition(request, pk, "submit")

    @action(detail=True, methods=["post"], url_path="review")
    def review(self, request, pk=None):
        return self._transition(request, pk, "review")

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        return self._transition(request, pk, "reject")

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        return self._transition(request, pk, "approve")

    @action(detail=True, methods=["post"], url_path="sign")
    def sign(self, request, pk=None):
        return self._transition(request, pk, "sign")

    @action(detail=True, methods=["post"], url_path="lock")
    def lock(self, request, pk=None):
        return self._transition(request, pk, "lock")

    def _transition(self, request, pk, action: str):
        report = self.get_object()
        serializer = ReportTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ip_address, user_agent = get_request_audit_context()
        updated = transition_report(
            report=report,
            action=action,
            actor=request.user,
            ip_address=ip_address,
            user_agent=user_agent,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(ReportSummarySerializer(updated).data)

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        report = self.get_object()
        if report.status not in {DailyReport.Status.APPROVED, DailyReport.Status.LOCKED}:
            return Response({"detail": "PDF export requires approved or locked state."}, status=400)
        file_bytes = build_report_pdf(report)
        response = HttpResponse(file_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="daily-report-{report.report_date}.pdf"'
        record_audit_event(
            actor=request.user,
            event_type="report.pdf.exported",
            object_type="DailyReport",
            object_id=str(report.id),
            project_id=str(report.project_id),
            metadata={"status": report.status},
        )
        return response

    @action(detail=True, methods=["post"], url_path="sync-weather")
    def sync_weather(self, request, pk=None):
        report = self.get_object()
        project = report.project
        if project.latitude is None or project.longitude is None:
            return Response({"detail": "Project coordinates are required to sync weather."}, status=400)
        params = urlencode(
            {
                "latitude": project.latitude,
                "longitude": project.longitude,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,weather_code",
                "timezone": "auto",
                "start_date": str(report.report_date),
                "end_date": str(report.report_date),
            }
        )
        url = f"https://api.open-meteo.com/v1/forecast?{params}"

        try:
            with urlopen(url, timeout=8) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            return Response({"detail": f"Weather sync failed: {exc}"}, status=502)

        daily = data.get("daily", {})
        report.weather_source = "open-meteo"
        report.temperature_high_c = _first_or_none(daily.get("temperature_2m_max"))
        report.temperature_low_c = _first_or_none(daily.get("temperature_2m_min"))
        report.precipitation_mm = _first_or_none(daily.get("precipitation_sum"))
        report.wind_max_kph = _first_or_none(daily.get("wind_speed_10m_max"))
        report.weather_summary = f"WMO code {str(_first_or_none(daily.get('weather_code')))}"
        report.save(
            update_fields=[
                "weather_source",
                "temperature_high_c",
                "temperature_low_c",
                "precipitation_mm",
                "wind_max_kph",
                "weather_summary",
                "updated_at",
            ]
        )
        record_audit_event(
            actor=request.user,
            event_type="report.weather.synced",
            object_type="DailyReport",
            object_id=str(report.id),
            project_id=str(report.project_id),
            metadata={"source": report.weather_source},
        )
        return Response(ReportSummarySerializer(report).data)


def _first_or_none(values):
    if isinstance(values, list) and values:
        return values[0]
    return None


class BaseReportEntryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filterset_fields = ("report",)
    ordering_fields = ("created_at",)

    def get_queryset(self):
        memberships = ProjectMembership.objects.filter(user=self.request.user, is_active=True).values_list(
            "project_id", flat=True
        )
        return self.queryset.filter(report__project_id__in=memberships)

    def perform_create(self, serializer):
        report = serializer.validated_data["report"]
        if report.status == DailyReport.Status.LOCKED:
            raise PermissionDenied("Locked reports cannot be changed.")
        if not user_has_project_role(
            self.request.user,
            str(report.project_id),
            (
                ProjectMembership.Role.FOREMAN,
                ProjectMembership.Role.SUPERINTENDENT,
                ProjectMembership.Role.ADMIN,
            ),
        ):
            raise PermissionDenied("Insufficient permissions.")
        serializer.save()

    def perform_update(self, serializer):
        report = serializer.instance.report
        if report.status == DailyReport.Status.LOCKED:
            raise PermissionDenied("Locked reports cannot be changed.")
        if not user_has_project_role(
            self.request.user,
            str(report.project_id),
            (
                ProjectMembership.Role.FOREMAN,
                ProjectMembership.Role.SUPERINTENDENT,
                ProjectMembership.Role.ADMIN,
            ),
        ):
            raise PermissionDenied("Insufficient permissions.")
        serializer.save()

    def perform_destroy(self, instance):
        report = instance.report
        if report.status == DailyReport.Status.LOCKED:
            raise PermissionDenied("Locked reports cannot be changed.")
        if not user_has_project_role(
            self.request.user,
            str(report.project_id),
            (
                ProjectMembership.Role.FOREMAN,
                ProjectMembership.Role.SUPERINTENDENT,
                ProjectMembership.Role.ADMIN,
            ),
        ):
            raise PermissionDenied("Insufficient permissions.")
        instance.delete()


class LaborEntryViewSet(BaseReportEntryViewSet):
    serializer_class = LaborEntrySerializer
    queryset = LaborEntry.objects.select_related("report", "report__project")


class EquipmentEntryViewSet(BaseReportEntryViewSet):
    serializer_class = EquipmentEntrySerializer
    queryset = EquipmentEntry.objects.select_related("report", "report__project")


class MaterialEntryViewSet(BaseReportEntryViewSet):
    serializer_class = MaterialEntrySerializer
    queryset = MaterialEntry.objects.select_related("report", "report__project")


class WorkLogEntryViewSet(BaseReportEntryViewSet):
    serializer_class = WorkLogEntrySerializer
    queryset = WorkLogEntry.objects.select_related("report", "report__project")


class DelayEntryViewSet(BaseReportEntryViewSet):
    serializer_class = DelayEntrySerializer
    queryset = DelayEntry.objects.select_related("report", "report__project")
