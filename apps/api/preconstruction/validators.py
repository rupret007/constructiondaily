"""Plan file (PDF) validation for uploads."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from rest_framework.exceptions import ValidationError


PLAN_ALLOWED_EXTENSIONS = {"pdf"}
PLAN_ALLOWED_MIME_TYPES = {"application/pdf"}
MAGIC_PDF = b"%PDF"


def validate_plan_upload(uploaded_file) -> tuple[str, str, int]:
    """
    Validate uploaded plan file: PDF only, extension, MIME, size, magic bytes.
    Returns (extension, mime_type, size).
    """
    original_name = uploaded_file.name or ""
    ext = Path(original_name).suffix.lower().lstrip(".")
    if ext not in PLAN_ALLOWED_EXTENSIONS:
        raise ValidationError("Only PDF plan files are allowed.")

    mime_type = uploaded_file.content_type or ""
    if mime_type not in PLAN_ALLOWED_MIME_TYPES:
        raise ValidationError("File must be a PDF (application/pdf).")

    size = uploaded_file.size or 0
    if size <= 0:
        raise ValidationError("Empty files are not allowed.")
    max_bytes = getattr(
        settings, "PLAN_UPLOAD_MAX_BYTES", settings.REPORT_ATTACHMENT_MAX_BYTES
    )
    if size > max_bytes:
        raise ValidationError("Plan file exceeds maximum size limit.")

    initial_bytes = uploaded_file.read(16)
    uploaded_file.seek(0)
    if not initial_bytes.startswith(MAGIC_PDF):
        raise ValidationError("File signature does not match PDF.")

    return ext, mime_type, size
