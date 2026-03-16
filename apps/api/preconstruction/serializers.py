"""Serializers for Preconstruction Plan Annotation."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework import serializers

from core.models import Project

from .filetypes import plan_file_extension_from_name, plan_file_type_from_storage_key
from .models import (
    AIAnalysisRun,
    AISuggestion,
    AnnotationItem,
    AnnotationLayer,
    ExportRecord,
    PlanSet,
    PlanSheet,
    ProjectDocument,
    RevisionSnapshot,
    TakeoffItem,
)
from .services import _normalize_estimator_quantity


class PreconstructionUserSlimSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "first_name", "last_name")


class PlanSetSerializer(serializers.ModelSerializer):
    created_by = PreconstructionUserSlimSerializer(read_only=True)
    updated_by = PreconstructionUserSlimSerializer(read_only=True)

    class Meta:
        model = PlanSet
        fields = (
            "id",
            "project",
            "name",
            "description",
            "status",
            "version_label",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")

    def validate(self, attrs):
        if self.instance and "project" in attrs and attrs["project"].id != self.instance.project_id:
            raise serializers.ValidationError("Project cannot be changed after plan set creation.")
        return attrs


class PlanSheetSerializer(serializers.ModelSerializer):
    created_by = PreconstructionUserSlimSerializer(read_only=True)
    file_extension = serializers.SerializerMethodField()
    file_type = serializers.SerializerMethodField()

    class Meta:
        model = PlanSheet
        fields = (
            "id",
            "project",
            "plan_set",
            "title",
            "sheet_number",
            "discipline",
            "storage_key",
            "page_count",
            "sheet_index",
            "width",
            "height",
            "calibrated_width",
            "calibrated_height",
            "calibrated_unit",
            "parse_status",
            "preview_image",
            "file_extension",
            "file_type",
            "created_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("project", "plan_set", "storage_key", "parse_status", "created_at", "updated_at")

    def validate(self, attrs):
        calibrated_width = attrs.get("calibrated_width")
        calibrated_height = attrs.get("calibrated_height")

        if self.instance:
            if "project" in attrs and attrs["project"].id != self.instance.project_id:
                raise serializers.ValidationError("Project cannot be changed after creation.")
            if "plan_set" in attrs and attrs["plan_set"].id != self.instance.plan_set_id:
                raise serializers.ValidationError("Plan set cannot be changed after creation.")

        width = calibrated_width if "calibrated_width" in attrs else getattr(self.instance, "calibrated_width", None)
        height = calibrated_height if "calibrated_height" in attrs else getattr(self.instance, "calibrated_height", None)

        if (width is None) != (height is None):
            raise serializers.ValidationError(
                "calibrated_width and calibrated_height must both be set, or both be empty."
            )
        if width is not None and Decimal(str(width)) <= 0:
            raise serializers.ValidationError("calibrated_width must be greater than zero.")
        if height is not None and Decimal(str(height)) <= 0:
            raise serializers.ValidationError("calibrated_height must be greater than zero.")
        return attrs

    def get_file_extension(self, obj) -> str:
        return plan_file_extension_from_name(getattr(obj, "storage_key", ""))

    def get_file_type(self, obj) -> str:
        return plan_file_type_from_storage_key(getattr(obj, "storage_key", ""))


class PlanSheetCreateSerializer(serializers.ModelSerializer):
    """Minimal fields for upload; plan_set and project come from request/URL."""

    class Meta:
        model = PlanSheet
        fields = ("title", "sheet_number", "discipline", "sheet_index")


class ProjectDocumentSerializer(serializers.ModelSerializer):
    created_by = PreconstructionUserSlimSerializer(read_only=True)
    updated_by = PreconstructionUserSlimSerializer(read_only=True)

    class Meta:
        model = ProjectDocument
        fields = (
            "id",
            "project",
            "plan_set",
            "title",
            "document_type",
            "original_filename",
            "storage_key",
            "mime_type",
            "file_extension",
            "size_bytes",
            "page_count",
            "parse_status",
            "parse_error",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "original_filename",
            "storage_key",
            "mime_type",
            "file_extension",
            "size_bytes",
            "page_count",
            "parse_status",
            "parse_error",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        if self.instance:
            if "project" in attrs and attrs["project"].id != self.instance.project_id:
                raise serializers.ValidationError("Project cannot be changed after creation.")
            if "plan_set" in attrs:
                incoming_plan_set = attrs.get("plan_set")
                incoming_plan_set_id = incoming_plan_set.id if incoming_plan_set else None
                if incoming_plan_set_id != self.instance.plan_set_id:
                    raise serializers.ValidationError("Plan set cannot be changed after creation.")

        project = attrs.get("project") or getattr(self.instance, "project", None)
        plan_set = attrs.get("plan_set") if "plan_set" in attrs else getattr(self.instance, "plan_set", None)
        if project and plan_set and plan_set.project_id != project.id:
            raise serializers.ValidationError("Plan set must belong to the selected project.")
        return attrs


class ProjectDocumentCreateSerializer(serializers.Serializer):
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())
    plan_set = serializers.PrimaryKeyRelatedField(queryset=PlanSet.objects.all(), required=False, allow_null=True)
    title = serializers.CharField(max_length=255, trim_whitespace=True, required=False, allow_blank=True)
    document_type = serializers.ChoiceField(choices=ProjectDocument.DocumentType.choices)

    def validate(self, attrs):
        project = attrs["project"]
        plan_set = attrs.get("plan_set")
        if plan_set and plan_set.project_id != project.id:
            raise serializers.ValidationError({"plan_set": "Plan set must belong to the selected project."})
        return attrs


class AnnotationLayerSerializer(serializers.ModelSerializer):
    created_by = PreconstructionUserSlimSerializer(read_only=True)

    class Meta:
        model = AnnotationLayer
        fields = (
            "id",
            "project",
            "plan_set",
            "plan_sheet",
            "name",
            "color",
            "category",
            "is_visible",
            "is_locked",
            "created_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")

    def validate(self, attrs):
        if self.instance:
            if "project" in attrs and attrs["project"].id != self.instance.project_id:
                raise serializers.ValidationError("Project cannot be changed after creation.")
            if "plan_set" in attrs and attrs["plan_set"].id != self.instance.plan_set_id:
                raise serializers.ValidationError("Plan set cannot be changed after creation.")
            if "plan_sheet" in attrs and attrs["plan_sheet"].id != self.instance.plan_sheet_id:
                raise serializers.ValidationError("Plan sheet cannot be changed after creation.")

        project = attrs.get("project") or getattr(self.instance, "project", None)
        plan_set = attrs.get("plan_set") or getattr(self.instance, "plan_set", None)
        plan_sheet = attrs.get("plan_sheet") or getattr(self.instance, "plan_sheet", None)

        if project and plan_set and plan_set.project_id != project.id:
            raise serializers.ValidationError("Plan set must belong to the selected project.")
        if project and plan_sheet and plan_sheet.project_id != project.id:
            raise serializers.ValidationError("Plan sheet must belong to the selected project.")
        if plan_set and plan_sheet and plan_sheet.plan_set_id != plan_set.id:
            raise serializers.ValidationError("Plan sheet must belong to the selected plan set.")
        return attrs


class AnnotationItemSerializer(serializers.ModelSerializer):
    created_by = PreconstructionUserSlimSerializer(read_only=True)
    updated_by = PreconstructionUserSlimSerializer(read_only=True)

    class Meta:
        model = AnnotationItem
        fields = (
            "id",
            "project",
            "plan_sheet",
            "layer",
            "annotation_type",
            "geometry_json",
            "label",
            "notes",
            "source",
            "confidence",
            "review_state",
            "linked_takeoff_item",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")

    def validate(self, attrs):
        if self.instance:
            if "project" in attrs and attrs["project"].id != self.instance.project_id:
                raise serializers.ValidationError("Project cannot be changed after creation.")
            if "plan_sheet" in attrs and attrs["plan_sheet"].id != self.instance.plan_sheet_id:
                raise serializers.ValidationError("Plan sheet cannot be changed after creation.")
            if "layer" in attrs and attrs["layer"].id != self.instance.layer_id:
                raise serializers.ValidationError("Layer cannot be changed after creation.")

        project = attrs.get("project") or getattr(self.instance, "project", None)
        plan_sheet = attrs.get("plan_sheet") or getattr(self.instance, "plan_sheet", None)
        layer = attrs.get("layer") or getattr(self.instance, "layer", None)

        if project and plan_sheet and plan_sheet.project_id != project.id:
            raise serializers.ValidationError("Plan sheet must belong to the selected project.")
        if project and layer and layer.project_id != project.id:
            raise serializers.ValidationError("Layer must belong to the selected project.")
        if plan_sheet and layer and layer.plan_sheet_id != plan_sheet.id:
            raise serializers.ValidationError("Layer must belong to the selected plan sheet.")
        return attrs


class TakeoffItemSerializer(serializers.ModelSerializer):
    created_by = PreconstructionUserSlimSerializer(read_only=True)
    updated_by = PreconstructionUserSlimSerializer(read_only=True)

    class Meta:
        model = TakeoffItem
        fields = (
            "id",
            "project",
            "plan_set",
            "plan_sheet",
            "category",
            "subcategory",
            "unit",
            "quantity",
            "confidence",
            "notes",
            "cost_code",
            "bid_package",
            "source",
            "review_state",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")

    def validate(self, attrs):
        if self.instance:
            if "project" in attrs and attrs["project"].id != self.instance.project_id:
                raise serializers.ValidationError("Project cannot be changed after creation.")
            if "plan_set" in attrs and attrs["plan_set"].id != self.instance.plan_set_id:
                raise serializers.ValidationError("Plan set cannot be changed after creation.")
            if "plan_sheet" in attrs:
                incoming_sheet = attrs.get("plan_sheet")
                incoming_sheet_id = incoming_sheet.id if incoming_sheet else None
                if incoming_sheet_id != self.instance.plan_sheet_id:
                    raise serializers.ValidationError("Plan sheet cannot be changed after creation.")

        project = attrs.get("project") or getattr(self.instance, "project", None)
        plan_set = attrs.get("plan_set") or getattr(self.instance, "plan_set", None)
        plan_sheet = attrs.get("plan_sheet") if "plan_sheet" in attrs else getattr(self.instance, "plan_sheet", None)

        if project and plan_set and plan_set.project_id != project.id:
            raise serializers.ValidationError("Plan set must belong to the selected project.")
        if plan_sheet:
            if project and plan_sheet.project_id != project.id:
                raise serializers.ValidationError("Plan sheet must belong to the selected project.")
            if plan_set and plan_sheet.plan_set_id != plan_set.id:
                raise serializers.ValidationError("Plan sheet must belong to the selected plan set.")

        normalize_quantity = self.instance is None or "quantity" in attrs or "unit" in attrs
        if normalize_quantity:
            quantity = attrs.get("quantity") if "quantity" in attrs else getattr(self.instance, "quantity", None)
            unit = attrs.get("unit") if "unit" in attrs else getattr(self.instance, "unit", TakeoffItem.Unit.COUNT)
            if quantity is not None:
                try:
                    attrs["quantity"] = _normalize_estimator_quantity(quantity, unit)
                except ValueError as exc:
                    raise serializers.ValidationError({"quantity": str(exc)})
        return attrs


class PreconstructionCopilotQuerySerializer(serializers.Serializer):
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())
    plan_set = serializers.PrimaryKeyRelatedField(queryset=PlanSet.objects.all(), required=False, allow_null=True)
    plan_sheet = serializers.PrimaryKeyRelatedField(queryset=PlanSheet.objects.all(), required=False, allow_null=True)
    annotation = serializers.PrimaryKeyRelatedField(queryset=AnnotationItem.objects.all(), required=False, allow_null=True)
    provider_name = serializers.ChoiceField(
        choices=(("mock", "Mock"), ("openai_vision", "OpenAI vision"), ("cad_dxf", "CAD DXF")),
        required=False,
        allow_null=True,
    )
    question = serializers.CharField(max_length=2000, trim_whitespace=True)

    def validate(self, attrs):
        project = attrs["project"]
        plan_set = attrs.get("plan_set")
        plan_sheet = attrs.get("plan_sheet")
        annotation = attrs.get("annotation")

        if not attrs.get("question", "").strip():
            raise serializers.ValidationError({"question": "This field may not be blank."})
        if plan_set and plan_set.project_id != project.id:
            raise serializers.ValidationError({"plan_set": "Plan set must belong to the selected project."})
        if plan_sheet and plan_sheet.project_id != project.id:
            raise serializers.ValidationError({"plan_sheet": "Plan sheet must belong to the selected project."})
        if annotation and annotation.project_id != project.id:
            raise serializers.ValidationError({"annotation": "Annotation must belong to the selected project."})
        if plan_set and plan_sheet and plan_sheet.plan_set_id != plan_set.id:
            raise serializers.ValidationError({"plan_sheet": "Plan sheet must belong to the selected plan set."})
        if annotation and plan_sheet and annotation.plan_sheet_id != plan_sheet.id:
            raise serializers.ValidationError({"annotation": "Annotation must belong to the selected sheet."})
        if annotation and plan_set and annotation.plan_sheet.plan_set_id != plan_set.id:
            raise serializers.ValidationError({"annotation": "Annotation must belong to the selected plan set."})
        return attrs


class PreconstructionCopilotCitationSerializer(serializers.Serializer):
    kind = serializers.CharField()
    id = serializers.CharField()
    label = serializers.CharField()
    detail = serializers.CharField()


class PreconstructionCopilotScopeSerializer(serializers.Serializer):
    project_id = serializers.CharField()
    project_code = serializers.CharField()
    project_name = serializers.CharField()
    plan_set_id = serializers.CharField(allow_blank=True, allow_null=True)
    plan_set_name = serializers.CharField(allow_blank=True, allow_null=True)
    plan_sheet_id = serializers.CharField(allow_blank=True, allow_null=True)
    plan_sheet_name = serializers.CharField(allow_blank=True, allow_null=True)


class PreconstructionCopilotActionPlanSerializer(serializers.Serializer):
    kind = serializers.CharField()
    label = serializers.CharField()
    detail = serializers.CharField()
    prompt = serializers.CharField(required=False)
    export_type = serializers.CharField(required=False)
    annotation_id = serializers.CharField(required=False)
    assembly_profile = serializers.CharField(required=False)
    snapshot_name = serializers.CharField(required=False)
    provider_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    min_confidence = serializers.FloatField(required=False)


class PreconstructionCopilotResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    answer = serializers.CharField()
    scope = PreconstructionCopilotScopeSerializer()
    citations = PreconstructionCopilotCitationSerializer(many=True)
    suggested_prompts = serializers.ListField(child=serializers.CharField(), required=False)
    action_plan = PreconstructionCopilotActionPlanSerializer(required=False)


class AIAnalysisRunSerializer(serializers.ModelSerializer):
    created_by = PreconstructionUserSlimSerializer(read_only=True)

    class Meta:
        model = AIAnalysisRun
        fields = (
            "id",
            "project",
            "plan_set",
            "plan_sheet",
            "provider_name",
            "user_prompt",
            "status",
            "request_payload_json",
            "response_payload_json",
            "started_at",
            "completed_at",
            "created_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "status",
            "request_payload_json",
            "response_payload_json",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        )


class AISuggestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AISuggestion
        fields = (
            "id",
            "analysis_run",
            "project",
            "plan_sheet",
            "suggestion_type",
            "geometry_json",
            "label",
            "rationale",
            "confidence",
            "accepted_annotation",
            "decision_state",
            "decided_by",
            "decided_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")


class RevisionSnapshotSerializer(serializers.ModelSerializer):
    created_by = PreconstructionUserSlimSerializer(read_only=True)

    class Meta:
        model = RevisionSnapshot
        fields = (
            "id",
            "project",
            "plan_set",
            "name",
            "status",
            "snapshot_payload_json",
            "created_by",
            "created_at",
        )
        read_only_fields = ("status", "snapshot_payload_json", "created_at")

    def validate(self, attrs):
        if self.instance:
            if "project" in attrs and attrs["project"].id != self.instance.project_id:
                raise serializers.ValidationError("Project cannot be changed after creation.")
            if "plan_set" in attrs and attrs["plan_set"].id != self.instance.plan_set_id:
                raise serializers.ValidationError("Plan set cannot be changed after creation.")

        project = attrs.get("project") or getattr(self.instance, "project", None)
        plan_set = attrs.get("plan_set") or getattr(self.instance, "plan_set", None)
        if project and plan_set and plan_set.project_id != project.id:
            raise serializers.ValidationError("Plan set must belong to the selected project.")
        return attrs


class ExportRecordSerializer(serializers.ModelSerializer):
    created_by = PreconstructionUserSlimSerializer(read_only=True)

    class Meta:
        model = ExportRecord
        fields = (
            "id",
            "project",
            "plan_set",
            "revision_snapshot",
            "export_type",
            "status",
            "storage_key",
            "metadata_json",
            "created_by",
            "created_at",
        )
        read_only_fields = ("storage_key", "metadata_json", "created_at")
