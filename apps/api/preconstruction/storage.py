"""Plan file storage under MEDIA_ROOT."""

from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings


def _plans_dir() -> Path:
    root = Path(settings.MEDIA_ROOT) / "plans"
    root.mkdir(parents=True, exist_ok=True)
    return root


def store_plan_file(uploaded_file, project_id: str, plan_set_id: str, extension: str) -> str:
    """
    Store an uploaded plan file under plans/<project_id>/<plan_set_id>/<uuid>.<ext>.
    Returns the storage_key (path relative to MEDIA_ROOT).
    """
    stored_name = f"{uuid.uuid4()}.{extension}"
    folder = _plans_dir() / str(project_id) / str(plan_set_id)
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / stored_name
    with file_path.open("wb") as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)
    return str(file_path.relative_to(settings.MEDIA_ROOT))


def get_plan_file_path(storage_key: str) -> Path:
    """Return full filesystem path for a storage_key."""
    return Path(settings.MEDIA_ROOT) / storage_key
