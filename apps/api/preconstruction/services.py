"""Business logic for Preconstruction: suggestions, snapshots, exports, audit."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.utils import timezone

from audit.services import record_audit_event

from .models import (
    AIAnalysisRun,
    AISuggestion,
    AnnotationItem,
    AnnotationLayer,
    PlanSet,
    PlanSheet,
    RevisionSnapshot,
    TakeoffItem,
)
from .providers.registry import get_provider


# ----- Audit helpers -----

def _record(event_type: str, actor, object_type: str, object_id: str, project_id: str, metadata: dict | None = None):
    record_audit_event(
        actor=actor,
        event_type=event_type,
        object_type=object_type,
        object_id=object_id,
        project_id=project_id,
        metadata=metadata or {},
    )


# ----- Suggestion accept / reject -----
# Learning signals (traceable feedback for future calibration; no active self-training):
# AISuggestion.decision_state, decided_by, decided_at, accepted_annotation; AnnotationItem
# (final geometry, label, source, review_state); TakeoffItem (category, unit, quantity, source,
# review_state); AIAnalysisRun request/response payloads; audit events below.

def accept_suggestion(
    suggestion_id: str,
    user,
    *,
    layer_id: str | None = None,
    geometry_json: dict | None = None,
    label: str | None = None,
    category: str | None = None,
    unit: str | None = None,
    quantity: str | Decimal | None = None,
) -> tuple[AnnotationItem, TakeoffItem]:
    """
    Accept an AI suggestion: create AnnotationItem and TakeoffItem, link them, update suggestion.
    If any override (geometry_json, label, category, unit, quantity) is provided, decision_state
    is set to EDITED and edit_ai_suggestion is audited; otherwise ACCEPTED and accept_ai_suggestion.
    These fields form the traceable feedback loop for future calibration (no active self-training).
    """
    suggestion = AISuggestion.objects.select_related("plan_sheet", "analysis_run").get(
        id=suggestion_id
    )
    if suggestion.decision_state != AISuggestion.DecisionState.PENDING:
        raise ValueError("Suggestion has already been decided.")

    plan_sheet = suggestion.plan_sheet
    project_id = str(plan_sheet.project_id)
    plan_set = plan_sheet.plan_set

    overrides_provided = (
        geometry_json is not None
        or label is not None
        or category is not None
        or unit is not None
        or quantity is not None
    )

    if layer_id:
        try:
            layer = AnnotationLayer.objects.get(id=layer_id, plan_sheet=plan_sheet)
        except AnnotationLayer.DoesNotExist:
            raise ValueError("Layer not found or not on this sheet.")
    else:
        layer = AnnotationLayer.objects.filter(plan_sheet=plan_sheet).first()
        if not layer:
            layer = AnnotationLayer.objects.create(
                project_id=plan_sheet.project_id,
                plan_set=plan_set,
                plan_sheet=plan_sheet,
                name="Default",
                created_by=user,
            )

    final_geometry = geometry_json if geometry_json is not None else suggestion.geometry_json
    final_label = label if label is not None else suggestion.label

    annotation = AnnotationItem.objects.create(
        project_id=plan_sheet.project_id,
        plan_sheet=plan_sheet,
        layer=layer,
        annotation_type=suggestion.suggestion_type,
        geometry_json=final_geometry,
        label=final_label or "",
        source=AnnotationItem.Source.AI,
        confidence=suggestion.confidence,
        review_state=AnnotationItem.ReviewState.EDITED if overrides_provided else AnnotationItem.ReviewState.ACCEPTED,
        created_by=user,
        updated_by=user,
    )

    qty = quantity
    if qty is None:
        qty = Decimal("1")
    elif isinstance(qty, str):
        try:
            qty = Decimal(qty)
        except InvalidOperation:
            raise ValueError("Invalid quantity.")
    if qty < 0:
        raise ValueError("Quantity must be non-negative.")

    takeoff = TakeoffItem.objects.create(
        project_id=plan_sheet.project_id,
        plan_set=plan_set,
        plan_sheet=plan_sheet,
        category=category or TakeoffItem.Category.CUSTOM,
        unit=unit or TakeoffItem.Unit.COUNT,
        quantity=qty,
        source=TakeoffItem.Source.AI_ASSISTED,
        review_state=TakeoffItem.ReviewState.EDITED if overrides_provided else TakeoffItem.ReviewState.ACCEPTED,
        created_by=user,
        updated_by=user,
    )
    annotation.linked_takeoff_item = takeoff
    annotation.save(update_fields=["linked_takeoff_item", "updated_at"])

    suggestion.accepted_annotation = annotation
    suggestion.decision_state = (
        AISuggestion.DecisionState.EDITED if overrides_provided else AISuggestion.DecisionState.ACCEPTED
    )
    suggestion.decided_by = user
    suggestion.decided_at = timezone.now()
    suggestion.save(update_fields=["accepted_annotation", "decision_state", "decided_by", "decided_at", "updated_at"])

    if overrides_provided:
        override_keys = []
        if geometry_json is not None:
            override_keys.append("geometry_json")
        if label is not None:
            override_keys.append("label")
        if category is not None:
            override_keys.append("category")
        if unit is not None:
            override_keys.append("unit")
        if quantity is not None:
            override_keys.append("quantity")
        _record(
            "edit_ai_suggestion",
            user,
            "AISuggestion",
            str(suggestion.id),
            project_id,
            {"annotation_id": str(annotation.id), "takeoff_id": str(takeoff.id), "overrides": override_keys},
        )
    else:
        _record(
            "accept_ai_suggestion",
            user,
            "AISuggestion",
            str(suggestion.id),
            project_id,
            {"annotation_id": str(annotation.id), "takeoff_id": str(takeoff.id)},
        )
    return annotation, takeoff


def run_plan_analysis(plan_sheet: PlanSheet, user_prompt: str, user, provider_name: str = "mock") -> AIAnalysisRun:
    """Create AIAnalysisRun, run provider, create AISuggestion rows, record audit."""
    run = AIAnalysisRun.objects.create(
        project=plan_sheet.project,
        plan_set=plan_sheet.plan_set,
        plan_sheet=plan_sheet,
        provider_name=provider_name,
        user_prompt=user_prompt or "",
        status=AIAnalysisRun.Status.RUNNING,
        request_payload_json={"user_prompt": user_prompt, "plan_sheet_id": str(plan_sheet.id)},
        created_by=user,
    )
    try:
        provider = get_provider(provider_name)
        suggestions_data = provider.run_analysis(plan_sheet, user_prompt)
        response_payload = {"suggestions": suggestions_data}
        for s in suggestions_data:
            AISuggestion.objects.create(
                analysis_run=run,
                project=plan_sheet.project,
                plan_sheet=plan_sheet,
                suggestion_type=s.get("suggestion_type", "rectangle"),
                geometry_json=s.get("geometry_json", {}),
                label=s.get("label", ""),
                rationale=s.get("rationale", ""),
                confidence=s.get("confidence"),
            )
        run.response_payload_json = response_payload
        run.status = AIAnalysisRun.Status.COMPLETED
    except Exception as e:
        run.status = AIAnalysisRun.Status.FAILED
        run.response_payload_json = {"error": str(e)}
    finally:
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "response_payload_json", "completed_at", "updated_at"])

    _record(
        "trigger_ai_analysis",
        user,
        "AIAnalysisRun",
        str(run.id),
        str(plan_sheet.project_id),
        {"status": run.status},
    )
    return run


def reject_suggestion(suggestion_id: str, user) -> AISuggestion:
    """Mark suggestion as rejected."""
    suggestion = AISuggestion.objects.get(id=suggestion_id)
    if suggestion.decision_state != AISuggestion.DecisionState.PENDING:
        raise ValueError("Suggestion has already been decided.")
    suggestion.decision_state = AISuggestion.DecisionState.REJECTED
    suggestion.decided_by = user
    suggestion.decided_at = timezone.now()
    suggestion.save(update_fields=["decision_state", "decided_by", "decided_at", "updated_at"])
    _record(
        "reject_ai_suggestion",
        user,
        "AISuggestion",
        str(suggestion.id),
        str(suggestion.project_id),
        {},
    )
    return suggestion


# ----- Snapshot -----

def build_snapshot_payload(plan_set: PlanSet) -> dict[str, Any]:
    """
    Build JSON payload for a revision snapshot (reproducible state).
    Captures plan set metadata, sheets, annotation layers/items (with source and review_state),
    takeoff items (with source and review_state), and AI suggestion outcomes per sheet so that
    locked snapshots serve as high-quality labeled data for future learning.
    """
    from .models import AISuggestion

    sheet_ids = list(plan_set.sheets.values_list("id", flat=True))
    suggestions_by_sheet: dict[str, list[dict[str, Any]]] = {str(sid): [] for sid in sheet_ids}
    if sheet_ids:
        for s in AISuggestion.objects.filter(plan_sheet_id__in=sheet_ids).select_related(
            "accepted_annotation"
        ):
            suggestions_by_sheet[str(s.plan_sheet_id)].append({
                "id": str(s.id),
                "decision_state": s.decision_state,
                "label": s.label,
                "suggestion_type": s.suggestion_type,
                "geometry_json": s.geometry_json,
                "rationale": s.rationale,
                "confidence": str(s.confidence) if s.confidence is not None else None,
                "accepted_annotation_id": str(s.accepted_annotation_id) if s.accepted_annotation_id else None,
                "decided_at": s.decided_at.isoformat() if s.decided_at else None,
            })

    sheets = []
    for sheet in plan_set.sheets.select_related().prefetch_related(
        "annotation_layers__items", "takeoff_items"
    ):
        layers_data = []
        for layer in sheet.annotation_layers.all():
            items_data = [
                {
                    "id": str(item.id),
                    "type": item.annotation_type,
                    "label": item.label,
                    "geometry_json": item.geometry_json,
                    "review_state": item.review_state,
                    "source": item.source,
                }
                for item in layer.items.all()
            ]
            layers_data.append({"id": str(layer.id), "name": layer.name, "items": items_data})
        takeoff_data = [
            {
                "id": str(t.id),
                "category": t.category,
                "unit": t.unit,
                "quantity": str(t.quantity),
                "sheet_id": str(sheet.id) if sheet else None,
                "source": t.source,
                "review_state": t.review_state,
            }
            for t in sheet.takeoff_items.all()
        ]
        sheets.append({
            "id": str(sheet.id),
            "title": sheet.title,
            "sheet_number": sheet.sheet_number,
            "layers": layers_data,
            "takeoff_items": takeoff_data,
            "ai_suggestion_outcomes": suggestions_by_sheet.get(str(sheet.id), []),
        })

    plan_set_takeoff = list(
        plan_set.takeoff_items.filter(plan_sheet__isnull=True).values(
            "id", "category", "unit", "quantity", "source", "review_state"
        )
    )
    for t in plan_set_takeoff:
        t["id"] = str(t["id"])
        t["quantity"] = str(t["quantity"])

    return {
        "plan_set_id": str(plan_set.id),
        "plan_set_name": plan_set.name,
        "plan_set_status": plan_set.status,
        "captured_at": timezone.now().isoformat(),
        "sheets": sheets,
        "plan_set_level_takeoff": plan_set_takeoff,
    }


# ----- Export -----

def create_export(
    plan_set: PlanSet,
    export_type: str,
    user,
    revision_snapshot: RevisionSnapshot | None = None,
) -> tuple[dict | str, str | None]:
    """
    Generate export payload (JSON dict or CSV string) and optional storage_key if saved.
    Returns (payload_for_response, storage_key or None).
    """
    from .models import ExportRecord

    payload = build_snapshot_payload(plan_set)
    storage_key = ""
    metadata = {"plan_set_id": str(plan_set.id), "export_type": export_type}

    if export_type == ExportRecord.ExportType.JSON:
        payload_str = json.dumps(payload, indent=2)
        # Optionally save to storage
        # storage_key = _save_export_file(plan_set, "json", payload_str.encode("utf-8"))
        return payload, None
    elif export_type == ExportRecord.ExportType.CSV:
        rows = []
        for sheet_data in payload.get("sheets", []):
            for t in sheet_data.get("takeoff_items", []):
                rows.append({
                    "sheet_id": sheet_data.get("id"),
                    "sheet_title": sheet_data.get("title"),
                    "takeoff_id": t.get("id"),
                    "category": t.get("category"),
                    "unit": t.get("unit"),
                    "quantity": t.get("quantity"),
                })
        for t in payload.get("plan_set_level_takeoff", []):
            rows.append({
                "sheet_id": "",
                "sheet_title": "",
                "takeoff_id": t.get("id"),
                "category": t.get("category"),
                "unit": t.get("unit"),
                "quantity": t.get("quantity"),
            })
        buf = io.StringIO()
        if rows:
            writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        csv_str = buf.getvalue()
        return csv_str, None
    elif export_type == ExportRecord.ExportType.PDF_METADATA:
        # Placeholder: true PDF generation not implemented; record metadata for audit.
        placeholder = {
            "message": "PDF export not implemented; metadata only.",
            "plan_set_id": str(plan_set.id),
            "plan_set_name": plan_set.name,
            "sheet_count": len(payload.get("sheets", [])),
            "captured_at": payload.get("captured_at"),
        }
        return placeholder, None
    else:
        return payload, None


def create_export_record(
    plan_set: PlanSet,
    export_type: str,
    user,
    status: str = "generated",
    revision_snapshot: RevisionSnapshot | None = None,
    storage_key: str = "",
    metadata_json: dict | None = None,
) -> "ExportRecord":
    from .models import ExportRecord

    record = ExportRecord.objects.create(
        project=plan_set.project,
        plan_set=plan_set,
        revision_snapshot=revision_snapshot,
        export_type=export_type,
        status=status,
        storage_key=storage_key or "",
        metadata_json=metadata_json or {},
        created_by=user,
    )
    _record(
        "generate_export",
        user,
        "ExportRecord",
        str(record.id),
        str(plan_set.project_id),
        {"export_type": export_type, "status": status},
    )
    return record
