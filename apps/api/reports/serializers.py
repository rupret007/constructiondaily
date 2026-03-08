from __future__ import annotations

from django.contrib.auth.models import User
from rest_framework import serializers

from core.models import Project
from files.models import Attachment
from reports.models import (
    ApprovalAction,
    DailyReport,
    DelayEntry,
    EquipmentEntry,
    LaborEntry,
    MaterialEntry,
    ReportSnapshot,
    WorkLogEntry,
)
from safety.models import SafetyEntry


class UserSlimSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "first_name", "last_name")


class ReportSummarySerializer(serializers.ModelSerializer):
    prepared_by = UserSlimSerializer(read_only=True)

    class Meta:
        model = DailyReport
        fields = (
            "id",
            "project",
            "report_date",
            "location",
            "prepared_by",
            "status",
            "summary",
            "weather_source",
            "weather_summary",
            "temperature_high_c",
            "temperature_low_c",
            "precipitation_mm",
            "wind_max_kph",
            "rejection_reason",
            "locked_at",
            "revision",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("status", "rejection_reason", "locked_at", "revision", "created_at", "updated_at")


class LaborEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LaborEntry
        fields = "__all__"


class EquipmentEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = EquipmentEntry
        fields = "__all__"


class MaterialEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = MaterialEntry
        fields = "__all__"


class WorkLogEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkLogEntry
        fields = "__all__"


class DelayEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = DelayEntry
        fields = "__all__"


class ReportSafetyEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = SafetyEntry
        fields = "__all__"


class ReportAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        fields = (
            "id",
            "report",
            "original_filename",
            "mime_type",
            "file_extension",
            "size_bytes",
            "sha256",
            "scan_status",
            "scan_detail",
            "created_at",
        )


class ApprovalActionSerializer(serializers.ModelSerializer):
    actor = UserSlimSerializer(read_only=True)

    class Meta:
        model = ApprovalAction
        fields = (
            "id",
            "report",
            "actor",
            "action",
            "reason",
            "signature_intent",
            "document_hash",
            "created_at",
        )


class ReportSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportSnapshot
        fields = ("id", "report", "revision", "file_path", "sha256", "created_at")


class DailyReportDetailSerializer(ReportSummarySerializer):
    labor_entries = LaborEntrySerializer(many=True, source="laborentry_set", read_only=True)
    equipment_entries = EquipmentEntrySerializer(many=True, source="equipmententry_set", read_only=True)
    material_entries = MaterialEntrySerializer(many=True, source="materialentry_set", read_only=True)
    work_entries = WorkLogEntrySerializer(many=True, source="worklogentry_set", read_only=True)
    delay_entries = DelayEntrySerializer(many=True, source="delayentry_set", read_only=True)
    safety_entries = ReportSafetyEntrySerializer(many=True, read_only=True)
    attachments = ReportAttachmentSerializer(many=True, read_only=True)
    approval_actions = ApprovalActionSerializer(many=True, read_only=True)
    snapshots = ReportSnapshotSerializer(many=True, read_only=True)

    class Meta(ReportSummarySerializer.Meta):
        fields = ReportSummarySerializer.Meta.fields + (
            "labor_entries",
            "equipment_entries",
            "material_entries",
            "work_entries",
            "delay_entries",
            "safety_entries",
            "attachments",
            "approval_actions",
            "snapshots",
        )


class ReportTransitionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    signature_intent = serializers.CharField(required=False, allow_blank=True, max_length=255)
