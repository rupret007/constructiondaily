from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel
from reports.models import DailyReport


class Attachment(TimeStampedModel):
    class ScanStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SCANNING = "scanning", "Scanning"
        SAFE = "safe", "Safe"
        QUARANTINED = "quarantined", "Quarantined"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey(DailyReport, on_delete=models.CASCADE, related_name="attachments")
    original_filename = models.CharField(max_length=255)
    stored_filename = models.CharField(max_length=255, unique=True)
    storage_key = models.CharField(max_length=512, unique=True)
    mime_type = models.CharField(max_length=128)
    file_extension = models.CharField(max_length=16)
    size_bytes = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attachments")
    scan_status = models.CharField(max_length=16, choices=ScanStatus.choices, default=ScanStatus.PENDING)
    scan_detail = models.TextField(blank=True)
    is_public = models.BooleanField(default=False)
    annotations_json = models.JSONField(null=True, blank=True, help_text="Stores overlay data (shapes, text, arrows) for images.")

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.scan_status})"


class UploadIntent(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey(DailyReport, on_delete=models.CASCADE, related_name="upload_intents")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="upload_intents")
    expires_at = models.DateTimeField()
    max_size_bytes = models.BigIntegerField()
    consumed = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at
