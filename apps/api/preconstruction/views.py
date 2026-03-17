"""ViewSets for Preconstruction Plan Annotation API."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from audit.services import record_audit_event
from core.models import Project, ProjectMembership
from core.permissions import user_has_project_role

from .cad import build_cad_preview
from .models import (
    AIAnalysisRun,
    AISuggestion,
    AnnotationItem,
    AnnotationLayer,
    ExportRecord,
    PlanSet,
    PlanSheet,
    ProjectDocument,
    ProjectTakeoffRule,
    RevisionSnapshot,
    TakeoffItem,
)
from .serializers import (
    AIAnalysisRunSerializer,
    AISuggestionSerializer,
    AnnotationItemSerializer,
    AnnotationLayerSerializer,
    ExportRecordSerializer,
    PlanSetEstimatingDashboardSerializer,
    PreconstructionCopilotQuerySerializer,
    PreconstructionCopilotResponseSerializer,
    PlanSetSerializer,
    PlanSheetCreateSerializer,
    PlanSheetSerializer,
    ProjectDocumentCreateSerializer,
    ProjectDocumentSerializer,
    RevisionSnapshotSerializer,
    ProjectTakeoffRuleSerializer,
    TakeoffItemSerializer,
)
from .services import (
    accept_suggestion,
    answer_preconstruction_question,
    batch_accept_suggestions,
    build_plan_set_estimating_dashboard,
    build_snapshot_payload,
    build_takeoff_summary,
    compute_snapshot_diff,
    create_export,
    create_export_record,
    create_takeoff_from_annotation,
    reject_suggestion,
    run_plan_analysis,
)
from .document_services import process_project_document
from .providers.registry import get_provider
from .filetypes import (
    plan_content_type_for_extension,
    plan_file_extension_from_name,
    plan_file_type_from_storage_key,
)
from .storage import (
    delete_project_document_file,
    get_plan_file_path,
    get_project_document_file_path,
    store_plan_file,
    store_project_document_file,
)
from .validators import validate_plan_upload, validate_project_document_upload


PROJECT_WRITE_ROLES = (
    ProjectMembership.Role.FOREMAN,
    ProjectMembership.Role.SUPERINTENDENT,
    ProjectMembership.Role.PROJECT_MANAGER,
    ProjectMembership.Role.ADMIN,
)


def _project_ids_for_user(user):
    return list(
        ProjectMembership.objects.filter(user=user, is_active=True).values_list(
            "project_id", flat=True
        )
    )


class PreconstructionCopilotViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "head", "options"]
    serializer_class = PreconstructionCopilotResponseSerializer

    @extend_schema(
        request=PreconstructionCopilotQuerySerializer,
        responses={200: PreconstructionCopilotResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="query")
    def query(self, request):
        serializer = PreconstructionCopilotQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        project = serializer.validated_data["project"]
        if project.id not in _project_ids_for_user(request.user):
            raise PermissionDenied("Insufficient permissions.")

        response_payload = answer_preconstruction_question(
            project=project,
            plan_set=serializer.validated_data.get("plan_set"),
            plan_sheet=serializer.validated_data.get("plan_sheet"),
            annotation=serializer.validated_data.get("annotation"),
            question=serializer.validated_data["question"],
            provider_name=serializer.validated_data.get("provider_name"),
        )
        return Response(
            PreconstructionCopilotResponseSerializer(response_payload).data,
            status=status.HTTP_200_OK,
        )


class PlanSetViewSet(viewsets.ModelViewSet):
    serializer_class = PlanSetSerializer
    queryset = PlanSet.objects.select_related("project", "created_by", "updated_by")
    permission_classes = [IsAuthenticated]
    filterset_fields = ("project", "status")
    ordering_fields = ("created_at", "name")

    def get_queryset(self):
        return self.queryset.filter(project_id__in=_project_ids_for_user(self.request.user))

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        if not user_has_project_role(self.request.user, str(project.id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        obj = serializer.save(created_by=self.request.user, updated_by=self.request.user)
        record_audit_event(
            actor=self.request.user,
            event_type="create_plan_set",
            object_type="PlanSet",
            object_id=str(obj.id),
            project_id=str(project.id),
            metadata={"name": obj.name},
        )

    def perform_update(self, serializer):
        obj = self.get_object()
        if not user_has_project_role(self.request.user, str(obj.project_id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        serializer.save(updated_by=self.request.user)
        record_audit_event(
            actor=self.request.user,
            event_type="update_plan_set",
            object_type="PlanSet",
            object_id=str(obj.id),
            project_id=str(obj.project_id),
            metadata={},
        )

    def perform_destroy(self, instance):
        if not user_has_project_role(self.request.user, str(instance.project_id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        record_audit_event(
            actor=self.request.user,
            event_type="delete_plan_set",
            object_type="PlanSet",
            object_id=str(instance.id),
            project_id=str(instance.project_id),
            metadata={},
        )
        instance.delete()


class PlanSheetViewSet(viewsets.ModelViewSet):
    serializer_class = PlanSheetSerializer
    queryset = PlanSheet.objects.select_related("project", "plan_set", "created_by")
    permission_classes = [IsAuthenticated]
    filterset_fields = ("project", "plan_set", "parse_status")
    ordering_fields = ("sheet_index", "created_at")

    def get_queryset(self):
        return self.queryset.filter(project_id__in=_project_ids_for_user(self.request.user))

    def create(self, request, *args, **kwargs):
        plan_set_id = request.data.get("plan_set")
        file_obj = request.FILES.get("file")
        if not plan_set_id or not file_obj:
            return Response(
                {"detail": "plan_set and file are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        plan_set = get_object_or_404(PlanSet, id=plan_set_id)
        if plan_set.project_id not in _project_ids_for_user(request.user):
            raise PermissionDenied("Insufficient permissions.")
        if not user_has_project_role(request.user, str(plan_set.project_id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        ext, _mime_type, _size = validate_plan_upload(file_obj)
        payload = {}
        for field in ("title", "sheet_number", "discipline", "sheet_index"):
            if field in request.data:
                payload[field] = request.data.get(field)
        payload_serializer = PlanSheetCreateSerializer(data=payload)
        payload_serializer.is_valid(raise_exception=True)
        validated = payload_serializer.validated_data
        storage_key = store_plan_file(file_obj, str(plan_set.project_id), str(plan_set.id), ext)
        sheet = PlanSheet.objects.create(
            project=plan_set.project,
            plan_set=plan_set,
            title=validated.get("title", ""),
            sheet_number=validated.get("sheet_number", ""),
            discipline=validated.get("discipline", ""),
            sheet_index=validated.get("sheet_index", 0),
            storage_key=storage_key,
            created_by=request.user,
        )
        record_audit_event(
            actor=request.user,
            event_type="upload_plan_sheet",
            object_type="PlanSheet",
            object_id=str(sheet.id),
            project_id=str(plan_set.project_id),
            metadata={"plan_set_id": str(plan_set.id)},
        )
        serializer = self.get_serializer(sheet)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        obj = self.get_object()
        if not user_has_project_role(self.request.user, str(obj.project_id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        serializer.save()
        record_audit_event(
            actor=self.request.user,
            event_type="update_plan_sheet",
            object_type="PlanSheet",
            object_id=str(obj.id),
            project_id=str(obj.project_id),
            metadata={},
        )

    def perform_destroy(self, instance):
        if not user_has_project_role(self.request.user, str(instance.project_id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        record_audit_event(
            actor=self.request.user,
            event_type="delete_plan_sheet",
            object_type="PlanSheet",
            object_id=str(instance.id),
            project_id=str(instance.project_id),
            metadata={"plan_set_id": str(instance.plan_set_id)},
        )
        instance.delete()

    @action(detail=True, methods=["get"], url_path="file")
    def file(self, request, pk=None):
        """Serve the uploaded plan file with permission check."""
        sheet = self.get_object()
        path = get_plan_file_path(sheet.storage_key)
        if not path.exists():
            return Response({"detail": "File not found."}, status=status.HTTP_404_NOT_FOUND)
        ext = plan_file_extension_from_name(sheet.storage_key) or "bin"
        filename = f"sheet-{sheet.id}.{ext}"
        return FileResponse(
            path.open("rb"),
            as_attachment=False,
            filename=filename,
            content_type=plan_content_type_for_extension(ext),
        )

    @action(detail=True, methods=["get"], url_path="cad_preview")
    def cad_preview(self, request, pk=None):
        """Return normalized CAD geometry for in-app canvas preview."""
        sheet = self.get_object()
        file_type = plan_file_type_from_storage_key(sheet.storage_key)
        if file_type not in {"dxf", "dwg"}:
            return Response(
                {"detail": "CAD preview is available for DXF/DWG sheets only."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            preview = build_cad_preview(sheet)
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(preview, status=status.HTTP_200_OK)


class ProjectDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectDocumentSerializer
    queryset = ProjectDocument.objects.select_related("project", "plan_set", "created_by", "updated_by")
    permission_classes = [IsAuthenticated]
    filterset_fields = ("project", "plan_set", "document_type", "parse_status")
    ordering_fields = ("created_at", "title")

    def get_queryset(self):
        queryset = self.queryset.filter(project_id__in=_project_ids_for_user(self.request.user))
        scope_plan_set = self.request.query_params.get("scope_plan_set")
        if scope_plan_set:
            queryset = queryset.filter(Q(plan_set_id=scope_plan_set) | Q(plan_set__isnull=True))
        return queryset

    def create(self, request, *args, **kwargs):
        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response({"detail": "file is required."}, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            "project": request.data.get("project"),
            "document_type": request.data.get("document_type"),
        }
        if "plan_set" in request.data:
            payload["plan_set"] = request.data.get("plan_set")
        if "title" in request.data:
            payload["title"] = request.data.get("title")

        payload_serializer = ProjectDocumentCreateSerializer(data=payload)
        payload_serializer.is_valid(raise_exception=True)
        validated = payload_serializer.validated_data
        project = validated["project"]
        plan_set = validated.get("plan_set")
        if project.id not in _project_ids_for_user(request.user):
            raise PermissionDenied("Insufficient permissions.")
        if not user_has_project_role(request.user, str(project.id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")

        ext, mime_type, size = validate_project_document_upload(file_obj)
        title = validated.get("title") or file_obj.name.rsplit(".", 1)[0]
        storage_key = store_project_document_file(
            file_obj,
            str(project.id),
            str(plan_set.id) if plan_set else None,
            ext,
        )
        document = ProjectDocument.objects.create(
            project=project,
            plan_set=plan_set,
            title=title.strip()[:255],
            document_type=validated["document_type"],
            original_filename=file_obj.name,
            storage_key=storage_key,
            mime_type=mime_type or "application/octet-stream",
            file_extension=ext,
            size_bytes=size,
            created_by=request.user,
            updated_by=request.user,
        )
        process_project_document(document)
        record_audit_event(
            actor=request.user,
            event_type="upload_project_document",
            object_type="ProjectDocument",
            object_id=str(document.id),
            project_id=str(project.id),
            metadata={
                "document_type": document.document_type,
                "plan_set_id": str(plan_set.id) if plan_set else "",
                "parse_status": document.parse_status,
            },
        )
        return Response(self.get_serializer(document).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        document = self.get_object()
        if not user_has_project_role(self.request.user, str(document.project_id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        serializer.save(updated_by=self.request.user)
        record_audit_event(
            actor=self.request.user,
            event_type="update_project_document",
            object_type="ProjectDocument",
            object_id=str(document.id),
            project_id=str(document.project_id),
            metadata={},
        )

    def perform_destroy(self, instance):
        if not user_has_project_role(self.request.user, str(instance.project_id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        storage_key = instance.storage_key
        record_audit_event(
            actor=self.request.user,
            event_type="delete_project_document",
            object_type="ProjectDocument",
            object_id=str(instance.id),
            project_id=str(instance.project_id),
            metadata={"document_type": instance.document_type},
        )
        instance.delete()
        delete_project_document_file(storage_key)

    @action(detail=True, methods=["get"], url_path="file")
    def file(self, request, pk=None):
        document = self.get_object()
        if document.parse_status != ProjectDocument.ParseStatus.PARSED:
            return Response(
                {"detail": "Only parsed project documents are available for download."},
                status=status.HTTP_409_CONFLICT,
            )
        path = get_project_document_file_path(document.storage_key)
        if not path.exists():
            return Response({"detail": "File not found."}, status=status.HTTP_404_NOT_FOUND)
        filename = document.original_filename or f"document-{document.id}.{document.file_extension}"
        return FileResponse(
            path.open("rb"),
            as_attachment=True,
            filename=filename,
            content_type=document.mime_type or "application/octet-stream",
        )


class AnnotationLayerViewSet(viewsets.ModelViewSet):
    serializer_class = AnnotationLayerSerializer
    queryset = AnnotationLayer.objects.select_related("project", "plan_set", "plan_sheet", "created_by")
    permission_classes = [IsAuthenticated]
    filterset_fields = ("project", "plan_set", "plan_sheet")
    ordering_fields = ("name",)

    def get_queryset(self):
        return self.queryset.filter(project_id__in=_project_ids_for_user(self.request.user))

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        if not user_has_project_role(self.request.user, str(project.id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        obj = serializer.save(created_by=self.request.user)
        record_audit_event(
            actor=self.request.user,
            event_type="create_annotation_layer",
            object_type="AnnotationLayer",
            object_id=str(obj.id),
            project_id=str(project.id),
            metadata={"name": obj.name},
        )

    def perform_update(self, serializer):
        obj = self.get_object()
        if not user_has_project_role(self.request.user, str(obj.project_id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        serializer.save()
        record_audit_event(
            actor=self.request.user,
            event_type="update_annotation_layer",
            object_type="AnnotationLayer",
            object_id=str(obj.id),
            project_id=str(obj.project_id),
            metadata={},
        )

    def perform_destroy(self, instance):
        if not user_has_project_role(self.request.user, str(instance.project_id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        record_audit_event(
            actor=self.request.user,
            event_type="delete_annotation_layer",
            object_type="AnnotationLayer",
            object_id=str(instance.id),
            project_id=str(instance.project_id),
            metadata={"name": instance.name},
        )
        instance.delete()


class AnnotationItemViewSet(viewsets.ModelViewSet):
    serializer_class = AnnotationItemSerializer
    queryset = AnnotationItem.objects.select_related(
        "project", "plan_sheet", "layer", "created_by", "updated_by"
    )
    permission_classes = [IsAuthenticated]
    filterset_fields = ("project", "plan_sheet", "layer", "source", "review_state")
    ordering_fields = ("created_at",)

    def get_queryset(self):
        return self.queryset.filter(project_id__in=_project_ids_for_user(self.request.user))

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        if not user_has_project_role(self.request.user, str(project.id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        obj = serializer.save(created_by=self.request.user, updated_by=self.request.user)
        record_audit_event(
            actor=self.request.user,
            event_type="create_annotation",
            object_type="AnnotationItem",
            object_id=str(obj.id),
            project_id=str(project.id),
            metadata={"annotation_type": obj.annotation_type},
        )

    def perform_update(self, serializer):
        obj = self.get_object()
        if not user_has_project_role(self.request.user, str(obj.project_id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        serializer.save(updated_by=self.request.user)
        record_audit_event(
            actor=self.request.user,
            event_type="update_annotation",
            object_type="AnnotationItem",
            object_id=str(obj.id),
            project_id=str(obj.project_id),
            metadata={},
        )

    def perform_destroy(self, instance):
        if not user_has_project_role(self.request.user, str(instance.project_id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        record_audit_event(
            actor=self.request.user,
            event_type="delete_annotation",
            object_type="AnnotationItem",
            object_id=str(instance.id),
            project_id=str(instance.project_id),
            metadata={},
        )
        instance.delete()

    @action(detail=True, methods=["post"], url_path="create_takeoff")
    def create_takeoff(self, request, pk=None):
        annotation = self.get_object()
        if not user_has_project_role(request.user, str(annotation.project_id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        assembly_profile = request.data.get("assembly_profile", "auto")
        try:
            primary, extras, resolved_profile = create_takeoff_from_annotation(
                str(annotation.id),
                request.user,
                assembly_profile=assembly_profile,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "primary_takeoff": TakeoffItemSerializer(primary).data,
                "extra_takeoffs": TakeoffItemSerializer(extras, many=True).data,
                "assembly_profile": resolved_profile,
            },
            status=status.HTTP_201_CREATED,
        )


class TakeoffItemViewSet(viewsets.ModelViewSet):
    serializer_class = TakeoffItemSerializer
    queryset = TakeoffItem.objects.select_related(
        "project", "plan_set", "plan_sheet", "created_by", "updated_by"
    )
    permission_classes = [IsAuthenticated]
    filterset_fields = (
        "project",
        "plan_set",
        "plan_sheet",
        "category",
        "source",
        "review_state",
        "cost_code",
        "bid_package",
    )
    ordering_fields = ("category", "created_at")

    def get_queryset(self):
        return self.queryset.filter(project_id__in=_project_ids_for_user(self.request.user))

    def _dashboard_queryset(self, request, plan_set: PlanSet):
        queryset = self.get_queryset().filter(plan_set=plan_set)
        for field in ("category", "source", "review_state", "cost_code", "bid_package"):
            value = request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})
        return queryset

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        if not request.query_params.get("plan_set"):
            return Response(
                {"detail": "plan_set is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        queryset = self.filter_queryset(self.get_queryset())
        return Response(build_takeoff_summary(queryset), status=status.HTTP_200_OK)

    @extend_schema(responses={200: PlanSetEstimatingDashboardSerializer})
    @action(detail=False, methods=["get"], url_path="dashboard")
    def dashboard(self, request):
        plan_set_id = request.query_params.get("plan_set")
        if not plan_set_id:
            return Response(
                {"detail": "plan_set is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        plan_set = get_object_or_404(PlanSet.objects.select_related("project"), id=plan_set_id)
        if plan_set.project_id not in _project_ids_for_user(request.user):
            raise PermissionDenied("Insufficient permissions.")
        payload = build_plan_set_estimating_dashboard(
            plan_set,
            queryset=self._dashboard_queryset(request, plan_set),
        )
        return Response(
            PlanSetEstimatingDashboardSerializer(payload).data,
            status=status.HTTP_200_OK,
        )

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        if not user_has_project_role(self.request.user, str(project.id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        obj = serializer.save(created_by=self.request.user, updated_by=self.request.user)
        record_audit_event(
            actor=self.request.user,
            event_type="create_takeoff_item",
            object_type="TakeoffItem",
            object_id=str(obj.id),
            project_id=str(project.id),
            metadata={"category": obj.category},
        )

    def perform_update(self, serializer):
        obj = self.get_object()
        if not user_has_project_role(self.request.user, str(obj.project_id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        serializer.save(updated_by=self.request.user)
        record_audit_event(
            actor=self.request.user,
            event_type="update_takeoff_item",
            object_type="TakeoffItem",
            object_id=str(obj.id),
            project_id=str(obj.project_id),
            metadata={},
        )

    def perform_destroy(self, instance):
        if not user_has_project_role(self.request.user, str(instance.project_id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        record_audit_event(
            actor=self.request.user,
            event_type="delete_takeoff_item",
            object_type="TakeoffItem",
            object_id=str(instance.id),
            project_id=str(instance.project_id),
            metadata={"category": instance.category},
        )
        instance.delete()


class AIAnalysisRunViewSet(viewsets.ModelViewSet):
    serializer_class = AIAnalysisRunSerializer
    queryset = AIAnalysisRun.objects.select_related(
        "project", "plan_set", "plan_sheet", "created_by"
    )
    permission_classes = [IsAuthenticated]
    filterset_fields = ("project", "plan_set", "plan_sheet", "status")
    ordering_fields = ("created_at",)
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return self.queryset.filter(project_id__in=_project_ids_for_user(self.request.user))

    def create(self, request, *args, **kwargs):
        plan_sheet_id = request.data.get("plan_sheet")
        user_prompt = request.data.get("user_prompt", "")
        provider_name = request.data.get("provider_name") or settings.PRECONSTRUCTION_ANALYSIS_PROVIDER or "mock"
        if not plan_sheet_id:
            return Response(
                {"detail": "plan_sheet is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            get_provider(provider_name)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        plan_sheet = get_object_or_404(PlanSheet, id=plan_sheet_id)
        if plan_sheet.project_id not in _project_ids_for_user(request.user):
            raise PermissionDenied("Insufficient permissions.")
        if not user_has_project_role(request.user, str(plan_sheet.project_id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        run = run_plan_analysis(plan_sheet, user_prompt, request.user, provider_name=provider_name)
        if run.status == AIAnalysisRun.Status.FAILED:
            error_message = "Analysis failed."
            if isinstance(run.response_payload_json, dict):
                payload_error = run.response_payload_json.get("error")
                if isinstance(payload_error, str) and payload_error.strip():
                    error_message = payload_error
            return Response(
                {"detail": error_message, "run_id": str(run.id), "status": run.status},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = self.get_serializer(run)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AISuggestionViewSet(viewsets.ModelViewSet):
    serializer_class = AISuggestionSerializer
    queryset = AISuggestion.objects.select_related(
        "analysis_run", "project", "plan_sheet", "accepted_annotation", "decided_by"
    )
    permission_classes = [IsAuthenticated]
    filterset_fields = ("project", "plan_sheet", "analysis_run", "decision_state")
    ordering_fields = ("created_at",)
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return self.queryset.filter(project_id__in=_project_ids_for_user(self.request.user))

    def create(self, request, *args, **kwargs):
        return Response(
            {"detail": "Direct suggestion creation is not allowed."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(detail=False, methods=["post"], url_path="batch_accept")
    def batch_accept(self, request):
        plan_sheet_id = request.data.get("plan_sheet")
        min_confidence = request.data.get("min_confidence", 0.85)
        if not plan_sheet_id:
            return Response(
                {"detail": "plan_sheet is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        plan_sheet = get_object_or_404(PlanSheet, id=plan_sheet_id)
        if plan_sheet.project_id not in _project_ids_for_user(request.user):
            raise PermissionDenied("Insufficient permissions.")
        if not user_has_project_role(request.user, str(plan_sheet.project_id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        try:
            min_conf = float(min_confidence)
        except (TypeError, ValueError):
            min_conf = 0.85
        results = batch_accept_suggestions(
            str(plan_sheet.id),
            request.user,
            min_confidence=min_conf,
        )
        return Response({
            "accepted_count": len(results),
            "annotations": [AnnotationItemSerializer(a).data for a, _ in results],
            "takeoff_items": [TakeoffItemSerializer(t).data for _, t in results],
        })

    @action(detail=True, methods=["post"], url_path="accept")
    def accept(self, request, pk=None):
        suggestion = self.get_object()
        if not user_has_project_role(request.user, str(suggestion.project_id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        if suggestion.decision_state != AISuggestion.DecisionState.PENDING:
            return Response(
                {"detail": "Suggestion has already been decided."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            annotation, takeoff = accept_suggestion(
                str(suggestion.id),
                request.user,
                layer_id=request.data.get("layer_id"),
                geometry_json=request.data.get("geometry_json") if "geometry_json" in request.data else None,
                label=request.data.get("label") if "label" in request.data else None,
                category=request.data.get("category") if "category" in request.data else None,
                unit=request.data.get("unit") if "unit" in request.data else None,
                quantity=request.data.get("quantity") if "quantity" in request.data else None,
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            "annotation": AnnotationItemSerializer(annotation).data,
            "takeoff": TakeoffItemSerializer(takeoff).data,
        })

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        suggestion = self.get_object()
        if not user_has_project_role(request.user, str(suggestion.project_id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        if suggestion.decision_state != AISuggestion.DecisionState.PENDING:
            return Response(
                {"detail": "Suggestion has already been decided."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            reject_suggestion(str(suggestion.id), request.user)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        suggestion.refresh_from_db()
        return Response(self.get_serializer(suggestion).data)

    @extend_schema(
        parameters=[
            {"name": "project", "in": "query", "required": True, "schema": {"type": "string", "format": "uuid"}},
            {"name": "plan_set", "in": "query", "required": False, "schema": {"type": "string", "format": "uuid"}},
        ],
        responses={200: {"description": "List of suggestion outcomes for calibration (labeled data)."}},
    )
    @action(detail=False, methods=["get"], url_path="feedback_export")
    def feedback_export(self, request):
        """Export AI suggestion outcomes (accept/edit/reject) for calibration or evaluation."""
        project_id = request.query_params.get("project")
        if not project_id:
            return Response(
                {"detail": "Query param 'project' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            project_uuid = uuid.UUID(project_id)
        except (TypeError, ValueError):
            return Response(
                {"detail": "Invalid project id."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if project_uuid not in _project_ids_for_user(request.user):
            raise PermissionDenied("Insufficient permissions.")
        qs = AISuggestion.objects.filter(project_id=project_uuid).select_related(
            "plan_sheet", "accepted_annotation"
        ).order_by("created_at")
        if request.query_params.get("plan_set"):
            qs = qs.filter(analysis_run__plan_set_id=request.query_params.get("plan_set"))
        rows = []
        for s in qs:
            row = {
                "id": str(s.id),
                "plan_sheet_id": str(s.plan_sheet_id),
                "label": s.label,
                "suggestion_type": s.suggestion_type,
                "decision_state": s.decision_state,
                "confidence": float(s.confidence) if s.confidence is not None else None,
                "decided_at": s.decided_at.isoformat() if s.decided_at else None,
            }
            if s.accepted_annotation_id:
                takeoff = TakeoffItem.objects.filter(
                    source_annotation_id=s.accepted_annotation_id
                ).first()
                if takeoff:
                    row["accepted_category"] = takeoff.category
                    row["accepted_unit"] = takeoff.unit
                    row["accepted_quantity"] = str(takeoff.quantity)
            rows.append(row)
        return Response(rows)


class ProjectTakeoffRuleViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectTakeoffRuleSerializer
    queryset = ProjectTakeoffRule.objects.select_related("project")
    permission_classes = [IsAuthenticated]
    filterset_fields = ("project", "trigger_category")
    ordering_fields = ("trigger_category", "name")

    def get_queryset(self):
        return self.queryset.filter(project_id__in=_project_ids_for_user(self.request.user))

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        if not user_has_project_role(self.request.user, str(project.id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        serializer.save()

    def perform_update(self, serializer):
        if not user_has_project_role(
            self.request.user,
            str(serializer.instance.project_id),
            PROJECT_WRITE_ROLES,
        ):
            raise PermissionDenied("Insufficient permissions.")
        serializer.save()

    def perform_destroy(self, instance):
        if not user_has_project_role(
            self.request.user,
            str(instance.project_id),
            PROJECT_WRITE_ROLES,
        ):
            raise PermissionDenied("Insufficient permissions.")
        instance.delete()


class RevisionSnapshotViewSet(viewsets.ModelViewSet):
    serializer_class = RevisionSnapshotSerializer
    queryset = RevisionSnapshot.objects.select_related("project", "plan_set", "created_by")
    permission_classes = [IsAuthenticated]
    filterset_fields = ("project", "plan_set", "status")
    ordering_fields = ("created_at",)
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return self.queryset.filter(project_id__in=_project_ids_for_user(self.request.user))

    def perform_create(self, serializer):
        plan_set = serializer.validated_data["plan_set"]
        if not user_has_project_role(self.request.user, str(plan_set.project_id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        with transaction.atomic():
            obj = serializer.save(
                created_by=self.request.user,
                status=RevisionSnapshot.Status.DRAFT,
            )
            obj.snapshot_payload_json = build_snapshot_payload(plan_set)
            obj.save(update_fields=["snapshot_payload_json"])
            record_audit_event(
                actor=self.request.user,
                event_type="create_revision_snapshot",
                object_type="RevisionSnapshot",
                object_id=str(obj.id),
                project_id=str(plan_set.project_id),
                metadata={"name": obj.name},
            )

    @action(detail=True, methods=["post"], url_path="lock")
    def lock(self, request, pk=None):
        snapshot = self.get_object()
        if not user_has_project_role(
            self.request.user,
            str(snapshot.project_id),
            (ProjectMembership.Role.PROJECT_MANAGER, ProjectMembership.Role.ADMIN),
        ):
            raise PermissionDenied("Insufficient permissions.")
        with transaction.atomic():
            snapshot = RevisionSnapshot.objects.select_for_update().get(pk=snapshot.pk)
            if snapshot.status == RevisionSnapshot.Status.LOCKED:
                return Response(
                    {"detail": "Snapshot is already locked."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            snapshot.status = RevisionSnapshot.Status.LOCKED
            snapshot.save(update_fields=["status", "updated_at"])
            record_audit_event(
                actor=request.user,
                event_type="lock_revision_snapshot",
                object_type="RevisionSnapshot",
                object_id=str(snapshot.id),
                project_id=str(snapshot.project_id),
                metadata={},
            )
        return Response(self.get_serializer(snapshot).data)

    @extend_schema(
        parameters=[
            {"name": "left", "in": "query", "required": True, "schema": {"type": "string"}, "description": "Snapshot ID (left side)."},
            {"name": "right", "in": "query", "required": True, "schema": {"type": "string"}, "description": "Snapshot ID or 'current' for live state (right side)."},
        ],
        responses={200: {"description": "Structured diff of takeoff and suggestion outcomes."}},
    )
    @action(detail=False, methods=["get"], url_path="diff")
    def diff(self, request):
        left_id = request.query_params.get("left")
        right_param = request.query_params.get("right")
        if not left_id or not right_param:
            return Response(
                {"detail": "Query params 'left' and 'right' are required. Use 'current' for right to compare to live state."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        left_snapshot = get_object_or_404(RevisionSnapshot, pk=left_id)
        if left_snapshot.project_id not in _project_ids_for_user(request.user):
            raise PermissionDenied("Insufficient permissions.")
        left_payload = left_snapshot.snapshot_payload_json or {}
        if right_param.strip().lower() == "current":
            plan_set = left_snapshot.plan_set
            if plan_set.project_id not in _project_ids_for_user(request.user):
                raise PermissionDenied("Insufficient permissions.")
            right_payload = build_snapshot_payload(plan_set)
        else:
            right_snapshot = get_object_or_404(RevisionSnapshot, pk=right_param)
            if right_snapshot.project_id not in _project_ids_for_user(request.user):
                raise PermissionDenied("Insufficient permissions.")
            if right_snapshot.plan_set_id != left_snapshot.plan_set_id:
                return Response(
                    {"detail": "Both snapshots must belong to the same plan set."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            right_payload = right_snapshot.snapshot_payload_json or {}
        result = compute_snapshot_diff(left_payload, right_payload)
        return Response(result)


class ExportRecordViewSet(viewsets.ModelViewSet):
    serializer_class = ExportRecordSerializer
    queryset = ExportRecord.objects.select_related(
        "project", "plan_set", "revision_snapshot", "created_by"
    )
    permission_classes = [IsAuthenticated]
    filterset_fields = ("project", "plan_set", "export_type", "status")
    ordering_fields = ("created_at",)
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return self.queryset.filter(project_id__in=_project_ids_for_user(self.request.user))

    def create(self, request, *args, **kwargs):
        plan_set_id = request.data.get("plan_set")
        export_type = request.data.get("export_type", ExportRecord.ExportType.JSON)
        revision_snapshot_id = request.data.get("revision_snapshot")
        if not plan_set_id:
            return Response(
                {"detail": "plan_set is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        plan_set = get_object_or_404(PlanSet, id=plan_set_id)
        if plan_set.project_id not in _project_ids_for_user(request.user):
            raise PermissionDenied("Insufficient permissions.")
        if not user_has_project_role(request.user, str(plan_set.project_id), PROJECT_WRITE_ROLES):
            raise PermissionDenied("Insufficient permissions.")
        allowed_export_types = {choice for choice, _ in ExportRecord.ExportType.choices}
        if export_type not in allowed_export_types:
            return Response(
                {"detail": f"Invalid export_type '{export_type}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        revision_snapshot = None
        if revision_snapshot_id:
            revision_snapshot = get_object_or_404(
                RevisionSnapshot,
                id=revision_snapshot_id,
                plan_set=plan_set,
            )
        payload, storage_key = create_export(plan_set, export_type, request.user, revision_snapshot)
        record = create_export_record(
            plan_set=plan_set,
            export_type=export_type,
            user=request.user,
            status=ExportRecord.Status.GENERATED,
            revision_snapshot=revision_snapshot,
            storage_key=storage_key or "",
        )
        if export_type == ExportRecord.ExportType.PDF_METADATA:
            safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in (plan_set.name or "takeoff"))
            filename = f"takeoff-{safe_name}.pdf"
            resp = HttpResponse(payload, content_type="application/pdf", status=200)
            resp["Content-Disposition"] = f'attachment; filename="{filename}"'
            return resp
        serializer = self.get_serializer(record)
        resp = Response(serializer.data, status=status.HTTP_201_CREATED)
        if export_type == ExportRecord.ExportType.JSON:
            resp.data["payload"] = payload
        elif export_type == ExportRecord.ExportType.CSV:
            resp.data["payload"] = payload
        return resp
