"""ViewSets for Preconstruction Plan Annotation API."""

from __future__ import annotations

from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from audit.services import record_audit_event
from core.models import ProjectMembership
from core.permissions import user_has_project_role

from .models import (
    AIAnalysisRun,
    AISuggestion,
    AnnotationItem,
    AnnotationLayer,
    ExportRecord,
    PlanSet,
    PlanSheet,
    RevisionSnapshot,
    TakeoffItem,
)
from .serializers import (
    AIAnalysisRunSerializer,
    AISuggestionSerializer,
    AnnotationItemSerializer,
    AnnotationLayerSerializer,
    ExportRecordSerializer,
    PlanSetSerializer,
    PlanSheetCreateSerializer,
    PlanSheetSerializer,
    RevisionSnapshotSerializer,
    TakeoffItemSerializer,
)
from .services import (
    accept_suggestion,
    batch_accept_suggestions,
    build_snapshot_payload,
    create_export,
    create_export_record,
    reject_suggestion,
    run_plan_analysis,
)
from .storage import get_plan_file_path, store_plan_file
from .validators import validate_plan_upload


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

    @action(detail=True, methods=["get"], url_path="file")
    def file(self, request, pk=None):
        """Serve the plan sheet PDF with permission check."""
        sheet = self.get_object()
        path = get_plan_file_path(sheet.storage_key)
        if not path.exists():
            return Response({"detail": "File not found."}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(path.open("rb"), as_attachment=False, filename=f"sheet-{sheet.id}.pdf")


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


class TakeoffItemViewSet(viewsets.ModelViewSet):
    serializer_class = TakeoffItemSerializer
    queryset = TakeoffItem.objects.select_related(
        "project", "plan_set", "plan_sheet", "created_by", "updated_by"
    )
    permission_classes = [IsAuthenticated]
    filterset_fields = ("project", "plan_set", "plan_sheet", "category", "source")
    ordering_fields = ("category", "created_at")

    def get_queryset(self):
        return self.queryset.filter(project_id__in=_project_ids_for_user(self.request.user))

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
        run = run_plan_analysis(plan_sheet, user_prompt, request.user)
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
        serializer = self.get_serializer(record)
        resp = Response(serializer.data, status=status.HTTP_201_CREATED)
        if export_type == ExportRecord.ExportType.JSON:
            resp.data["payload"] = payload
        elif export_type == ExportRecord.ExportType.CSV:
            resp.data["payload"] = payload
        elif export_type == ExportRecord.ExportType.PDF_METADATA:
            resp.data["payload"] = payload
        return resp
