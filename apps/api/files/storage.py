from __future__ import annotations

import os
import uuid
from pathlib import Path

from django.conf import settings


def _resolve_storage_path(storage_key: str) -> Path:
    """Resolve storage_key under MEDIA_ROOT; raise ValueError if it escapes (e.g. '..')."""
    if not storage_key or ".." in storage_key:
        raise ValueError("Invalid storage_key.")
    base = Path(settings.MEDIA_ROOT).resolve()
    path = (base / storage_key).resolve()
    try:
        path.relative_to(base)
    except ValueError:
        raise ValueError("storage_key resolves outside MEDIA_ROOT.")
    return path


def _base_dir() -> Path:
    root = Path(settings.MEDIA_ROOT) / "attachments"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _stage_path(stage: str) -> Path:
    path = _base_dir() / stage
    path.mkdir(parents=True, exist_ok=True)
    return path


def store_in_stage(uploaded_file, extension: str, stage: str = "raw") -> tuple[str, str]:
    stored_name = f"{uuid.uuid4()}.{extension}"
    folder = _stage_path(stage)
    file_path = folder / stored_name
    with file_path.open("wb") as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)
    storage_key = str(file_path.relative_to(settings.MEDIA_ROOT))
    return stored_name, storage_key


def promote_to_safe(storage_key: str) -> str:
    source = _resolve_storage_path(storage_key)
    safe_folder = _stage_path("safe")
    target = safe_folder / source.name
    source.replace(target)
    return str(target.relative_to(settings.MEDIA_ROOT))


def quarantine(storage_key: str) -> str:
    source = _resolve_storage_path(storage_key)
    quarantine_folder = _stage_path("quarantine")
    target = quarantine_folder / source.name
    source.replace(target)
    return str(target.relative_to(settings.MEDIA_ROOT))


def delete_storage_key(storage_key: str) -> None:
    if not storage_key:
        return
    try:
        file_path = _resolve_storage_path(storage_key)
    except ValueError:
        return
    if file_path.exists():
        file_path.unlink()
