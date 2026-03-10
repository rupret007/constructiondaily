from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from audit.services import record_audit_event
from core.models import ProjectMembership
from core.permissions import user_has_project_role
from files.models import Attachment, UploadIntent
from files.serializers import AttachmentSerializer, UploadIntentSerializer
from files.storage import promote_to_safe, quarantine, store_in_stage
from files.validators import validate_upload
from reports.models import DailyReport


class AttachmentViewSet(viewsets.ModelViewSet):
    serializer_class = AttachmentSerializer
    queryset = Attachment.objects.select_related("report", "uploaded_by")
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "delete", "head", "options"]
    filterset_fields = ("report", "scan_status")

    def get_queryset(self):
        memberships = ProjectMembership.objects.filter(user=self.request.user, is_active=True).values_list(
            "project_id", flat=True
        )
        return self.queryset.filter(report__project_id__in=memberships)

    def create(self, request, *args, **kwargs):
        report_id = request.data.get("report")
        uploaded_file = request.FILES.get("file")
        if not report_id or not uploaded_file:
            return Response({"detail": "Both report and file are required."}, status=status.HTTP_400_BAD_REQUEST)

        report = get_object_or_404(DailyReport, id=report_id)
        result = _create_attachment(
            request_user=request.user,
            report=report,
            uploaded_file=uploaded_file,
            enforce_intent_limit=False,
        )
        if isinstance(result, Response):
            return result
        serializer = self.get_serializer(result)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        if instance.report.status == DailyReport.Status.LOCKED:
            raise PermissionDenied("Locked reports cannot be changed.")
        if not _can_upload_to_project(self.request.user, str(instance.report.project_id)):
            raise PermissionDenied("Insufficient permissions.")
        project_id = str(instance.report.project_id)
        attachment_id = str(instance.id)
        instance.delete()
        record_audit_event(
            actor=self.request.user,
            event_type="attachment.deleted",
            object_type="Attachment",
            object_id=attachment_id,
            project_id=project_id,
            metadata={"attachment_id": attachment_id},
        )

    @action(detail=True, methods=["post"], url_path="scan-result")
    def scan_result(self, request, pk=None):
        attachment = self.get_object()
        result = request.data.get("result")
        detail = request.data.get("detail", "")

        if not user_has_project_role(
            request.user,
            str(attachment.report.project_id),
            (ProjectMembership.Role.ADMIN, ProjectMembership.Role.SAFETY),
        ):
            return Response({"detail": "Insufficient permissions."}, status=status.HTTP_403_FORBIDDEN)

        if result == "safe":
            attachment.storage_key = promote_to_safe(attachment.storage_key)
            attachment.scan_status = Attachment.ScanStatus.SAFE
        elif result == "quarantined":
            attachment.storage_key = quarantine(attachment.storage_key)
            attachment.scan_status = Attachment.ScanStatus.QUARANTINED
        else:
            return Response({"detail": "Invalid scan result."}, status=status.HTTP_400_BAD_REQUEST)
        attachment.scan_detail = detail
        attachment.save(update_fields=["storage_key", "scan_status", "scan_detail", "updated_at"])

        record_audit_event(
            actor=request.user,
            event_type="attachment.scanned",
            object_type="Attachment",
            object_id=str(attachment.id),
            project_id=str(attachment.report.project_id),
            metadata={"result": attachment.scan_status},
        )
        return Response(self.get_serializer(attachment).data)


class UploadIntentViewSet(viewsets.ModelViewSet):
    serializer_class = UploadIntentSerializer
    queryset = UploadIntent.objects.select_related("report", "created_by")
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "get"]
    filterset_fields = ("report", "consumed")

    def get_queryset(self):
        memberships = ProjectMembership.objects.filter(user=self.request.user, is_active=True).values_list(
            "project_id", flat=True
        )
        return self.queryset.filter(report__project_id__in=memberships)

    def create(self, request, *args, **kwargs):
        report_id = request.data.get("report")
        if not report_id:
            return Response({"detail": "Report is required."}, status=status.HTTP_400_BAD_REQUEST)
        report = get_object_or_404(DailyReport, id=report_id)
        if not _can_upload_to_project(request.user, str(report.project_id)):
            return Response({"detail": "Insufficient permissions."}, status=status.HTTP_403_FORBIDDEN)

        raw_max_size = request.data.get("max_size_bytes", 10 * 1024 * 1024)
        try:
            max_size = int(raw_max_size)
        except (TypeError, ValueError):
            return Response({"detail": "max_size_bytes must be a positive integer."}, status=status.HTTP_400_BAD_REQUEST)
        if max_size <= 0:
            return Response({"detail": "max_size_bytes must be a positive integer."}, status=status.HTTP_400_BAD_REQUEST)

        intent = UploadIntent.objects.create(
            report=report,
            created_by=request.user,
            expires_at=timezone.now() + timedelta(minutes=10),
            max_size_bytes=max_size,
        )

        record_audit_event(
            actor=request.user,
            event_type="upload.intent.created",
            object_type="UploadIntent",
            object_id=str(intent.id),
            project_id=str(report.project_id),
            metadata={"expires_at": intent.expires_at.isoformat()},
        )
        return Response(self.get_serializer(intent).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="upload")
    def upload(self, request, pk=None):
        intent_for_access = self.get_object()
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response({"detail": "File is required."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            intent = UploadIntent.objects.select_related("report").select_for_update().get(pk=intent_for_access.pk)
            if intent.consumed:
                return Response({"detail": "Upload intent already used."}, status=status.HTTP_400_BAD_REQUEST)
            if intent.is_expired:
                return Response({"detail": "Upload intent is expired."}, status=status.HTTP_400_BAD_REQUEST)

            result = _create_attachment(
                request_user=request.user,
                report=intent.report,
                uploaded_file=uploaded_file,
                enforce_intent_limit=True,
                intent_max_size=intent.max_size_bytes,
            )
            if isinstance(result, Response):
                return result

            intent.consumed = True
            intent.save(update_fields=["consumed", "updated_at"])
        return Response(AttachmentSerializer(result).data, status=status.HTTP_201_CREATED)


def _can_upload_to_project(user, project_id: str) -> bool:
    return user_has_project_role(
        user,
        project_id,
        (
            ProjectMembership.Role.FOREMAN,
            ProjectMembership.Role.SUPERINTENDENT,
            ProjectMembership.Role.PROJECT_MANAGER,
            ProjectMembership.Role.ADMIN,
        ),
    )


def _create_attachment(request_user, report: DailyReport, uploaded_file, enforce_intent_limit: bool, intent_max_size: int = 0):
    if report.status == DailyReport.Status.LOCKED:
        return Response({"detail": "Cannot upload files to locked report."}, status=status.HTTP_400_BAD_REQUEST)
    if not _can_upload_to_project(request_user, str(report.project_id)):
        return Response({"detail": "Insufficient permissions."}, status=status.HTTP_403_FORBIDDEN)

    extension, mime_type, size, sha256 = validate_upload(uploaded_file)
    if enforce_intent_limit and size > intent_max_size:
        return Response({"detail": "File exceeds upload intent size limit."}, status=status.HTTP_400_BAD_REQUEST)

    stored_filename, storage_key = store_in_stage(uploaded_file, extension, "raw")
    attachment = Attachment.objects.create(
        report=report,
        original_filename=uploaded_file.name,
        stored_filename=stored_filename,
        storage_key=storage_key,
        mime_type=mime_type,
        file_extension=extension,
        size_bytes=size,
        sha256=sha256,
        uploaded_by=request_user,
        scan_status=Attachment.ScanStatus.PENDING,
    )

    record_audit_event(
        actor=request_user,
        event_type="attachment.uploaded",
        object_type="Attachment",
        object_id=str(attachment.id),
        project_id=str(report.project_id),
        metadata={"scan_status": attachment.scan_status},
    )
    return attachment
