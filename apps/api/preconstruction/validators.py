"""Plan file validation for uploads (PDF + DXF)."""

from __future__ import annotations

from django.conf import settings
from rest_framework.exceptions import ValidationError

from .filetypes import plan_file_extension_from_name

PLAN_ALLOWED_EXTENSIONS = {"pdf", "dxf", "dwg"}
PLAN_ALLOWED_MIME_TYPES_BY_EXTENSION = {
    "pdf": {"application/pdf"},
    "dxf": {
        "application/dxf",
        "application/x-dxf",
        "image/vnd.dxf",
        "text/plain",
        "application/octet-stream",
    },
    "dwg": {
        "application/acad",
        "application/x-acad",
        "image/vnd.dwg",
        "application/octet-stream",
    },
}
MAGIC_PDF = b"%PDF"
DXF_SIGNATURE_TOKENS = ("SECTION", "ENTITIES", "EOF")
DWG_MAGIC_PREFIX = b"AC10"
PROJECT_DOCUMENT_ALLOWED_EXTENSIONS = {"pdf", "txt", "md"}
PROJECT_DOCUMENT_ALLOWED_MIME_TYPES_BY_EXTENSION = {
    "pdf": {"application/pdf"},
    "txt": {"text/plain", "application/octet-stream"},
    "md": {"text/markdown", "text/plain", "application/octet-stream"},
}


def _looks_like_dxf(initial_bytes: bytes) -> bool:
    try:
        content = initial_bytes.decode("utf-8", errors="ignore").upper()
    except Exception:
        return False
    if "DXF" in content and "SECTION" in content:
        return True
    # ASCII DXF is code/value pairs; these markers are expected near file start.
    return all(token in content for token in DXF_SIGNATURE_TOKENS[:2])


def validate_plan_upload(uploaded_file) -> tuple[str, str, int]:
    """
    Validate uploaded plan file (PDF/DXF): extension, MIME, size, signature.
    Returns (extension, mime_type, size).
    """
    original_name = uploaded_file.name or ""
    ext = plan_file_extension_from_name(original_name)
    if ext not in PLAN_ALLOWED_EXTENSIONS:
        raise ValidationError("Only PDF, DXF, or DWG plan files are allowed.")

    mime_type = (uploaded_file.content_type or "").split(";")[0].strip().lower()
    allowed_mimes = PLAN_ALLOWED_MIME_TYPES_BY_EXTENSION.get(ext, set())
    if mime_type and mime_type not in allowed_mimes:
        if ext == "pdf":
            raise ValidationError("File must be a PDF (application/pdf).")
        if ext == "dxf":
            raise ValidationError("File must be a DXF (application/dxf or equivalent).")
        raise ValidationError("File must be a DWG (application/acad or equivalent).")

    size = uploaded_file.size or 0
    if size <= 0:
        raise ValidationError("Empty files are not allowed.")
    max_bytes = getattr(
        settings, "PLAN_UPLOAD_MAX_BYTES", settings.REPORT_ATTACHMENT_MAX_BYTES
    )
    if size > max_bytes:
        raise ValidationError("Plan file exceeds maximum size limit.")

    initial_bytes = uploaded_file.read(65536)
    uploaded_file.seek(0)
    if ext == "pdf" and not initial_bytes.startswith(MAGIC_PDF):
        raise ValidationError("File signature does not match PDF.")
    if ext == "dxf" and not _looks_like_dxf(initial_bytes):
        raise ValidationError("File signature does not match DXF.")
    if ext == "dwg" and not initial_bytes.startswith(DWG_MAGIC_PREFIX):
        raise ValidationError("File signature does not match DWG.")

    return ext, mime_type, size


def validate_project_document_upload(uploaded_file) -> tuple[str, str, int]:
    """
    Validate uploaded project document (PDF, TXT, MD).
    Returns (extension, mime_type, size).
    """
    original_name = uploaded_file.name or ""
    ext = plan_file_extension_from_name(original_name)
    if ext not in PROJECT_DOCUMENT_ALLOWED_EXTENSIONS:
        raise ValidationError("Only PDF, TXT, or MD project documents are allowed.")

    mime_type = (uploaded_file.content_type or "").split(";")[0].strip().lower()
    allowed_mimes = PROJECT_DOCUMENT_ALLOWED_MIME_TYPES_BY_EXTENSION.get(ext, set())
    if mime_type and mime_type not in allowed_mimes:
        raise ValidationError(f"File MIME type is not allowed for .{ext} documents.")

    size = uploaded_file.size or 0
    if size <= 0:
        raise ValidationError("Empty files are not allowed.")
    max_bytes = getattr(
        settings,
        "PROJECT_DOCUMENT_UPLOAD_MAX_BYTES",
        getattr(settings, "PLAN_UPLOAD_MAX_BYTES", settings.REPORT_ATTACHMENT_MAX_BYTES),
    )
    if size > max_bytes:
        raise ValidationError("Project document exceeds maximum size limit.")

    initial_bytes = uploaded_file.read(65536)
    uploaded_file.seek(0)
    if ext == "pdf" and not initial_bytes.startswith(MAGIC_PDF):
        raise ValidationError("File signature does not match PDF.")
    if ext in {"txt", "md"}:
        try:
            initial_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationError("Text project documents must be valid UTF-8.") from exc

    return ext, mime_type, size
