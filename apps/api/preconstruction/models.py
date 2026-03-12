"""Models for Preconstruction Plan Annotation and Takeoff."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from core.models import Project, TimeStampedModel


class PlanSet(TimeStampedModel):
    """Named collection of plan sheets for a project (e.g. bid package or estimate version)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="plan_sets")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT)
    version_label = models.CharField(max_length=64, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_plan_sets",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_plan_sets",
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.project.code} — {self.name}"


class PlanSheet(TimeStampedModel):
    """Uploaded drawing file (PDF sheet or DXF CAD file)."""

    class ParseStatus(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        PARSED = "parsed", "Parsed"
        INDEXED = "indexed", "Indexed"
        FAILED = "failed", "Failed"

    class CalibrationUnit(models.TextChoices):
        FEET = "feet", "Feet"
        METERS = "meters", "Meters"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="plan_sheets")
    plan_set = models.ForeignKey(PlanSet, on_delete=models.CASCADE, related_name="sheets")
    title = models.CharField(max_length=255, blank=True)
    sheet_number = models.CharField(max_length=64, blank=True)
    discipline = models.CharField(max_length=64, blank=True)
    storage_key = models.CharField(max_length=512)
    page_count = models.PositiveIntegerField(default=1)
    sheet_index = models.PositiveIntegerField(default=0)
    width = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    height = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    calibrated_width = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    calibrated_height = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    calibrated_unit = models.CharField(
        max_length=16,
        choices=CalibrationUnit.choices,
        default=CalibrationUnit.FEET,
    )
    parse_status = models.CharField(
        max_length=32, choices=ParseStatus.choices, default=ParseStatus.UPLOADED
    )
    preview_image = models.CharField(max_length=512, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_plan_sheets",
    )

    class Meta:
        ordering = ("sheet_index", "created_at")

    def __str__(self) -> str:
        return f"{self.plan_set.name} — {self.title or self.sheet_number or str(self.id)[:8]}"


class AnnotationLayer(TimeStampedModel):
    """Logical layer of annotations on a sheet (visibility, lock, category)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="annotation_layers")
    plan_set = models.ForeignKey(PlanSet, on_delete=models.CASCADE, related_name="annotation_layers")
    plan_sheet = models.ForeignKey(
        PlanSheet, on_delete=models.CASCADE, related_name="annotation_layers"
    )
    name = models.CharField(max_length=255)
    color = models.CharField(max_length=32, blank=True)
    category = models.CharField(max_length=64, blank=True)
    is_visible = models.BooleanField(default=True)
    is_locked = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_annotation_layers",
    )

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return f"{self.name} ({self.plan_sheet})"


class AnnotationItem(TimeStampedModel):
    """Single annotation: point, rectangle, polygon, polyline, or text note."""

    class AnnotationType(models.TextChoices):
        POINT = "point", "Point"
        RECTANGLE = "rectangle", "Rectangle"
        POLYGON = "polygon", "Polygon"
        POLYLINE = "polyline", "Polyline"
        TEXT = "text", "Text"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        AI = "ai", "AI"

    class ReviewState(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        EDITED = "edited", "Edited"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="annotation_items")
    plan_sheet = models.ForeignKey(
        PlanSheet, on_delete=models.CASCADE, related_name="annotation_items"
    )
    layer = models.ForeignKey(
        AnnotationLayer, on_delete=models.CASCADE, related_name="items"
    )
    annotation_type = models.CharField(max_length=32, choices=AnnotationType.choices)
    geometry_json = models.JSONField(default=dict)
    label = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    source = models.CharField(max_length=32, choices=Source.choices, default=Source.MANUAL)
    confidence = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True
    )
    review_state = models.CharField(
        max_length=32, choices=ReviewState.choices, default=ReviewState.PENDING
    )
    linked_takeoff_item = models.OneToOneField(
        "TakeoffItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_annotation",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_annotation_items",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_annotation_items",
    )

    class Meta:
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"{self.annotation_type} — {self.label or self.id}"


class TakeoffItem(TimeStampedModel):
    """Estimator quantity record (count, area, length, etc.) linked optionally to an annotation."""

    class Category(models.TextChoices):
        DOORS = "doors", "Doors"
        DOOR_HARDWARE = "door_hardware", "Door hardware"
        WINDOWS = "windows", "Windows"
        OPENINGS = "openings", "Openings"
        ROOMS = "rooms", "Rooms"
        PLUMBING_FIXTURES = "plumbing_fixtures", "Plumbing fixtures"
        ELECTRICAL_FIXTURES = "electrical_fixtures", "Electrical fixtures"
        CONCRETE_AREAS = "concrete_areas", "Concrete areas"
        LINEAR_MEASUREMENTS = "linear_measurements", "Linear measurements"
        CUSTOM = "custom", "Custom"

    class Unit(models.TextChoices):
        COUNT = "count", "Count"
        SQUARE_FEET = "square_feet", "Square feet"
        LINEAR_FEET = "linear_feet", "Linear feet"
        CUBIC_YARDS = "cubic_yards", "Cubic yards"
        EACH = "each", "Each"
        CUSTOM = "custom", "Custom"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        AI_ASSISTED = "ai_assisted", "AI assisted"

    class ReviewState(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        EDITED = "edited", "Edited"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="takeoff_items")
    plan_set = models.ForeignKey(PlanSet, on_delete=models.CASCADE, related_name="takeoff_items")
    plan_sheet = models.ForeignKey(
        PlanSheet,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="takeoff_items",
    )
    category = models.CharField(max_length=64, choices=Category.choices, default=Category.CUSTOM)
    subcategory = models.CharField(max_length=128, blank=True)
    unit = models.CharField(max_length=32, choices=Unit.choices, default=Unit.COUNT)
    quantity = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    confidence = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True
    )
    notes = models.TextField(blank=True)
    cost_code = models.CharField(max_length=64, blank=True)
    bid_package = models.CharField(max_length=128, blank=True)
    source = models.CharField(max_length=32, choices=Source.choices, default=Source.MANUAL)
    review_state = models.CharField(
        max_length=32, choices=ReviewState.choices, default=ReviewState.PENDING
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_takeoff_items",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_takeoff_items",
    )

    class Meta:
        ordering = ("category", "created_at")

    def __str__(self) -> str:
        return f"{self.category} — {self.quantity} {self.unit}"


class AIAnalysisRun(TimeStampedModel):
    """One AI-assisted analysis request on a plan sheet."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        SUPERSEDED = "superseded", "Superseded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="ai_analysis_runs")
    plan_set = models.ForeignKey(PlanSet, on_delete=models.CASCADE, related_name="ai_analysis_runs")
    plan_sheet = models.ForeignKey(
        PlanSheet, on_delete=models.CASCADE, related_name="ai_analysis_runs"
    )
    provider_name = models.CharField(max_length=64)
    user_prompt = models.TextField(blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.QUEUED)
    request_payload_json = models.JSONField(default=dict, blank=True)
    response_payload_json = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_ai_analysis_runs",
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.provider_name} on {self.plan_sheet} ({self.status})"


class AISuggestion(TimeStampedModel):
    """One candidate suggestion from an AI analysis run; user can accept, reject, or edit."""

    class DecisionState(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        EDITED = "edited", "Edited"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analysis_run = models.ForeignKey(
        AIAnalysisRun, on_delete=models.CASCADE, related_name="suggestions"
    )
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="ai_suggestions")
    plan_sheet = models.ForeignKey(
        PlanSheet, on_delete=models.CASCADE, related_name="ai_suggestions"
    )
    suggestion_type = models.CharField(max_length=32)
    geometry_json = models.JSONField(default=dict)
    label = models.CharField(max_length=255, blank=True)
    rationale = models.TextField(blank=True)
    confidence = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True
    )
    accepted_annotation = models.ForeignKey(
        AnnotationItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_from_suggestion",
    )
    decision_state = models.CharField(
        max_length=32, choices=DecisionState.choices, default=DecisionState.PENDING
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decided_ai_suggestions",
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"{self.label or self.suggestion_type} ({self.decision_state})"


class RevisionSnapshot(TimeStampedModel):
    """Saved state of plan set and takeoff summary for reproducibility and export."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        LOCKED = "locked", "Locked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="revision_snapshots")
    plan_set = models.ForeignKey(
        PlanSet, on_delete=models.CASCADE, related_name="revision_snapshots"
    )
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT)
    snapshot_payload_json = models.JSONField(default=dict)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_revision_snapshots",
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.plan_set.name} — {self.name} ({self.status})"


class ExportRecord(TimeStampedModel):
    """Record of an export (JSON, CSV, etc.) for audit and download."""

    class ExportType(models.TextChoices):
        JSON = "json", "JSON"
        CSV = "csv", "CSV"
        PDF_METADATA = "pdf_metadata", "PDF metadata"

    class Status(models.TextChoices):
        GENERATED = "generated", "Generated"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="export_records")
    plan_set = models.ForeignKey(PlanSet, on_delete=models.CASCADE, related_name="export_records")
    revision_snapshot = models.ForeignKey(
        RevisionSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="export_records",
    )
    export_type = models.CharField(max_length=32, choices=ExportType.choices)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.GENERATED)
    storage_key = models.CharField(max_length=512, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_export_records",
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.plan_set.name} — {self.export_type} ({self.status})"
