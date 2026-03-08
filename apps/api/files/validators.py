from __future__ import annotations

import hashlib
from pathlib import Path

from django.conf import settings
from rest_framework.exceptions import ValidationError


MAGIC_SIGNATURES = {
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "webp": [b"RIFF"],  # validated with WEBP header suffix check
    "pdf": [b"%PDF"],
}


def validate_upload(uploaded_file) -> tuple[str, str, int, str]:
    original_name = uploaded_file.name or ""
    ext = Path(original_name).suffix.lower().lstrip(".")
    if ext not in settings.REPORT_ALLOWED_EXTENSIONS:
        raise ValidationError("File extension is not allowed.")

    mime_type = uploaded_file.content_type or ""
    if mime_type not in settings.REPORT_ALLOWED_MIME_TYPES:
        raise ValidationError("MIME type is not allowed.")

    size = uploaded_file.size or 0
    if size <= 0:
        raise ValidationError("Empty files are not allowed.")
    if size > settings.REPORT_ATTACHMENT_MAX_BYTES:
        raise ValidationError("File exceeds maximum size limit.")

    initial_bytes = uploaded_file.read(16)
    uploaded_file.seek(0)
    signatures = MAGIC_SIGNATURES.get(ext, [])
    if not any(initial_bytes.startswith(sig) for sig in signatures):
        raise ValidationError("File signature does not match extension.")
    if ext == "webp" and initial_bytes[8:12] != b"WEBP":
        raise ValidationError("WEBP signature is invalid.")

    sha256_hash = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        sha256_hash.update(chunk)
    uploaded_file.seek(0)

    return ext, mime_type, size, sha256_hash.hexdigest()
