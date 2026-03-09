"""Serializers for Preconstruction Plan Annotation."""

from __future__ import annotations

from django.contrib.auth.models import User
from rest_framework import serializers

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


class PlanSheetSerializer(serializers.ModelSerializer):
    created_by = PreconstructionUserSlimSerializer(read_only=True)

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
            "parse_status",
            "preview_image",
            "created_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("storage_key", "parse_status", "created_at", "updated_at")


class PlanSheetCreateSerializer(serializers.ModelSerializer):
    """Minimal fields for upload; plan_set and project come from request/URL."""

    class Meta:
        model = PlanSheet
        fields = ("title", "sheet_number", "discipline", "sheet_index")


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
        read_only_fields = ("snapshot_payload_json", "created_at")


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
