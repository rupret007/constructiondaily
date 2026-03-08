from __future__ import annotations

import uuid

from django.db import models

from core.models import TimeStampedModel
from reports.models import DailyReport


class SafetyEntry(TimeStampedModel):
    class EntryType(models.TextChoices):
        INCIDENT = "incident", "Incident"
        NEAR_MISS = "near_miss", "Near Miss"
        OBSERVATION = "observation", "Observation"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey(DailyReport, on_delete=models.CASCADE, related_name="safety_entries")
    entry_type = models.CharField(max_length=16, choices=EntryType.choices)
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.LOW)
    description = models.TextField()
    corrective_action = models.TextField(blank=True)
    closed = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)
