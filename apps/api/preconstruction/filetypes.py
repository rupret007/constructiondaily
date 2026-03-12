"""Helpers for preconstruction plan file type detection and response metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

PlanFileType = Literal["pdf", "dxf", "dwg", "unknown"]

_PLAN_CONTENT_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "dxf": "application/dxf",
    "dwg": "application/acad",
}


def plan_file_extension_from_name(name: str) -> str:
    return Path(name or "").suffix.lower().lstrip(".")


def plan_file_type_from_extension(extension: str) -> PlanFileType:
    ext = (extension or "").strip().lower()
    if ext == "pdf":
        return "pdf"
    if ext == "dxf":
        return "dxf"
    if ext == "dwg":
        return "dwg"
    return "unknown"


def plan_file_type_from_storage_key(storage_key: str) -> PlanFileType:
    return plan_file_type_from_extension(plan_file_extension_from_name(storage_key))


def plan_content_type_for_extension(extension: str) -> str:
    ext = (extension or "").strip().lower()
    return _PLAN_CONTENT_TYPES.get(ext, "application/octet-stream")
