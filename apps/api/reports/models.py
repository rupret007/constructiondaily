from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import Project, TimeStampedModel


class DailyReport(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        REVIEWED = "reviewed", "Reviewed"
        APPROVED = "approved", "Approved"
        LOCKED = "locked", "Locked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="daily_reports")
    report_date = models.DateField(default=timezone.localdate)
    location = models.CharField(max_length=255)
    prepared_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="prepared_reports")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    summary = models.TextField(blank=True)
    weather_source = models.CharField(max_length=64, blank=True)
    weather_summary = models.CharField(max_length=255, blank=True)
    temperature_high_c = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    temperature_low_c = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    precipitation_mm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    wind_max_kph = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="locked_reports",
    )
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("project", "report_date"), name="unique_project_daily_report")]
        ordering = ("-report_date", "-created_at")

    def __str__(self) -> str:
        return f"{self.project.code} {self.report_date} ({self.status})"


class BaseReportEntry(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey(DailyReport, on_delete=models.CASCADE)
    notes = models.TextField(blank=True)

    class Meta:
        abstract = True


class LaborEntry(BaseReportEntry):
    trade = models.CharField(max_length=128)
    company = models.CharField(max_length=128, blank=True)
    workers = models.PositiveIntegerField()
    regular_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    overtime_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    cost_code = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ("trade",)


class EquipmentEntry(BaseReportEntry):
    equipment_name = models.CharField(max_length=128)
    quantity = models.PositiveIntegerField(default=1)
    hours_used = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    downtime_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    downtime_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("equipment_name",)


class MaterialEntry(BaseReportEntry):
    material_name = models.CharField(max_length=128)
    unit = models.CharField(max_length=32, default="unit")
    quantity_delivered = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantity_used = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    supplier = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ("material_name",)


class WorkLogEntry(BaseReportEntry):
    area = models.CharField(max_length=128)
    activity = models.CharField(max_length=255)
    quantity_completed = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    unit = models.CharField(max_length=32, blank=True)
    percent_complete = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    schedule_impact = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("area", "activity")


class DelayEntry(BaseReportEntry):
    class Category(models.TextChoices):
        WEATHER = "weather", "Weather"
        DESIGN = "design", "Design"
        DELIVERY = "delivery", "Delivery"
        LABOR = "labor", "Labor"
        OWNER = "owner", "Owner"
        OTHER = "other", "Other"

    category = models.CharField(max_length=32, choices=Category.choices, default=Category.OTHER)
    cause = models.CharField(max_length=255)
    impact = models.TextField()
    mitigation = models.TextField(blank=True)
    hours_lost = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    class Meta:
        ordering = ("category",)


class ApprovalAction(TimeStampedModel):
    class Action(models.TextChoices):
        SUBMIT = "submit", "Submit"
        REVIEW = "review", "Review"
        REJECT = "reject", "Reject"
        APPROVE = "approve", "Approve"
        LOCK = "lock", "Lock"
        SIGN = "sign", "Sign"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey(DailyReport, on_delete=models.CASCADE, related_name="approval_actions")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="approval_actions")
    action = models.CharField(max_length=16, choices=Action.choices)
    reason = models.TextField(blank=True)
    signature_intent = models.CharField(max_length=255, blank=True)
    document_hash = models.CharField(max_length=128, blank=True)
    actor_ip = models.GenericIPAddressField(null=True, blank=True)
    actor_user_agent = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("created_at",)


class ReportSnapshot(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey(DailyReport, on_delete=models.CASCADE, related_name="snapshots")
    revision = models.PositiveIntegerField()
    file_path = models.CharField(max_length=512)
    sha256 = models.CharField(max_length=64)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("report", "revision"), name="unique_report_revision_snapshot"),
        ]
