"""Plan file storage under MEDIA_ROOT."""

from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings


def _plans_dir() -> Path:
    root = Path(settings.MEDIA_ROOT) / "plans"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _project_documents_dir() -> Path:
    root = Path(settings.MEDIA_ROOT) / "project_documents"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _project_document_scope_dir(project_id: str, plan_set_id: str | None, stage: str | None = None) -> Path:
    scope = str(plan_set_id) if plan_set_id else "project"
    folder = _project_documents_dir() / str(project_id) / scope
    if stage:
        folder = folder / stage
    folder.mkdir(parents=True, exist_ok=True)
    return folder


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


def store_project_document_file(
    uploaded_file,
    project_id: str,
    plan_set_id: str | None,
    extension: str,
    stage: str = "raw",
) -> str:
    """
    Store an uploaded project document under project_documents/<project>/<scope>/<stage>/<uuid>.<ext>.
    Returns the storage_key relative to MEDIA_ROOT.
    """
    stored_name = f"{uuid.uuid4()}.{extension}"
    folder = _project_document_scope_dir(project_id, plan_set_id, stage=stage)
    file_path = folder / stored_name
    with file_path.open("wb") as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)
    return str(file_path.relative_to(settings.MEDIA_ROOT))


def _move_project_document_file(storage_key: str, project_id: str, plan_set_id: str | None, stage: str) -> str:
    source = Path(settings.MEDIA_ROOT) / storage_key
    if not source.exists():
        return storage_key
    target_folder = _project_document_scope_dir(project_id, plan_set_id, stage=stage)
    target = target_folder / source.name
    if source != target:
        source.replace(target)
    return str(target.relative_to(settings.MEDIA_ROOT))


def promote_project_document_to_safe(storage_key: str, project_id: str, plan_set_id: str | None) -> str:
    return _move_project_document_file(storage_key, project_id, plan_set_id, "safe")


def quarantine_project_document_file(storage_key: str, project_id: str, plan_set_id: str | None) -> str:
    return _move_project_document_file(storage_key, project_id, plan_set_id, "quarantine")


def get_project_document_file_path(storage_key: str) -> Path:
    return Path(settings.MEDIA_ROOT) / storage_key


def delete_project_document_file(storage_key: str) -> None:
    path = get_project_document_file_path(storage_key)
    if path.exists():
        path.unlink()
