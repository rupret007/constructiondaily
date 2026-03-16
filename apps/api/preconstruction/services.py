"""Business logic for Preconstruction: suggestions, snapshots, exports, audit."""

from __future__ import annotations

import csv
import io
import json
import math
import re
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from audit.services import record_audit_event

from .models import (
    AIAnalysisRun,
    AISuggestion,
    AnnotationItem,
    AnnotationLayer,
    ExportRecord,
    PlanSet,
    PlanSheet,
    ProjectDocument,
    RevisionSnapshot,
    TakeoffItem,
)
from .document_services import search_project_documents
from .filetypes import plan_file_type_from_storage_key
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


# ----- Category–unit defaults (CSI-aligned) -----
# Map suggestion label / type to default TakeoffItem category and unit for estimator workflow.
LABEL_TO_CATEGORY_UNIT: dict[str, tuple[str, str]] = {
    "door": (TakeoffItem.Category.DOORS, TakeoffItem.Unit.COUNT),
    "doors": (TakeoffItem.Category.DOORS, TakeoffItem.Unit.COUNT),
    "window": (TakeoffItem.Category.WINDOWS, TakeoffItem.Unit.COUNT),
    "windows": (TakeoffItem.Category.WINDOWS, TakeoffItem.Unit.COUNT),
    "plumbing fixture": (TakeoffItem.Category.PLUMBING_FIXTURES, TakeoffItem.Unit.COUNT),
    "fixture": (TakeoffItem.Category.PLUMBING_FIXTURES, TakeoffItem.Unit.COUNT),
    "fixtures": (TakeoffItem.Category.PLUMBING_FIXTURES, TakeoffItem.Unit.COUNT),
    "electrical fixture": (TakeoffItem.Category.ELECTRICAL_FIXTURES, TakeoffItem.Unit.COUNT),
    "concrete area": (TakeoffItem.Category.CONCRETE_AREAS, TakeoffItem.Unit.SQUARE_FEET),
    "concrete slab": (TakeoffItem.Category.CONCRETE_AREAS, TakeoffItem.Unit.SQUARE_FEET),
    "opening": (TakeoffItem.Category.OPENINGS, TakeoffItem.Unit.COUNT),
    "openings": (TakeoffItem.Category.OPENINGS, TakeoffItem.Unit.COUNT),
    "room": (TakeoffItem.Category.ROOMS, TakeoffItem.Unit.COUNT),
    "rooms": (TakeoffItem.Category.ROOMS, TakeoffItem.Unit.COUNT),
    "linear measurement": (TakeoffItem.Category.LINEAR_MEASUREMENTS, TakeoffItem.Unit.LINEAR_FEET),
}

ASSEMBLY_PROFILE_AUTO = "auto"
ASSEMBLY_PROFILE_NONE = "none"
ASSEMBLY_PROFILE_DOOR_SET = "door_set"
ASSEMBLY_PROFILE_WINDOW_SET = "window_set"
ASSEMBLY_PROFILE_FIXTURE_SET = "fixture_set"
SUPPORTED_ASSEMBLY_PROFILES = {
    ASSEMBLY_PROFILE_AUTO,
    ASSEMBLY_PROFILE_NONE,
    ASSEMBLY_PROFILE_DOOR_SET,
    ASSEMBLY_PROFILE_WINDOW_SET,
    ASSEMBLY_PROFILE_FIXTURE_SET,
}

COPILOT_DOCUMENT_KEYWORDS = (
    "spec",
    "specs",
    "specification",
    "specifications",
    "rfi",
    "rfis",
    "submittal",
    "submittals",
    "addendum",
    "addenda",
    "vendor",
    "vendors",
    "cut sheet",
    "cutsheet",
    "scope letter",
    "bid instruction",
)
COPILOT_HELP_KEYWORDS = (
    "what can you do",
    "what can i ask",
    "help me",
    "how can you help",
    "capabilities",
)
COPILOT_PLAN_SET_KEYWORDS = ("plan set", "plan sets", "version", "versions", "bid set", "bid sets")
COPILOT_SHEET_KEYWORDS = ("sheet", "sheets", "drawing", "drawings", "plan", "plans")
COPILOT_TAKEOFF_KEYWORDS = ("takeoff", "take off", "count", "counts", "quantity", "quantities", "how many", "total")
COPILOT_ANALYSIS_KEYWORDS = ("analysis", "analyze", "suggestion", "suggestions", "ai run", "ai", "vision")
COPILOT_SNAPSHOT_KEYWORDS = ("snapshot", "snapshots", "revision", "revisions", "lock", "locked", "compare", "changed", "difference")
COPILOT_EXPORT_KEYWORDS = ("export", "exports", "csv", "json", "download")
COPILOT_FILETYPE_KEYWORDS = ("cad", "pdf", "dwg", "dxf", "file type", "file types")
COPILOT_DOCUMENT_INTENT_KEYWORDS = (
    "called for",
    "required",
    "specified",
    "specifies",
    "per spec",
    "per specs",
    "manufacturer",
    "model",
    "finish",
    "fire rating",
    "package",
)

COPILOT_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        TakeoffItem.Category.DOOR_HARDWARE,
        ("door hardware", "hardware", "doorknob", "doorknobs", "door knob", "door knobs"),
    ),
    (TakeoffItem.Category.DOORS, ("door", "doors")),
    (TakeoffItem.Category.WINDOWS, ("window", "windows")),
    (TakeoffItem.Category.OPENINGS, ("opening", "openings")),
    (TakeoffItem.Category.ROOMS, ("room", "rooms")),
    (
        TakeoffItem.Category.PLUMBING_FIXTURES,
        ("plumbing fixture", "plumbing fixtures", "fixture", "fixtures", "plumbing"),
    ),
    (
        TakeoffItem.Category.ELECTRICAL_FIXTURES,
        ("electrical fixture", "electrical fixtures", "light fixture", "light fixtures", "electrical"),
    ),
    (TakeoffItem.Category.CONCRETE_AREAS, ("concrete", "slab", "slabs", "area", "areas")),
    (TakeoffItem.Category.LINEAR_MEASUREMENTS, ("linear", "length", "run", "runs", "lf")),
]

COPILOT_REVIEW_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (TakeoffItem.ReviewState.PENDING, ("pending", "needs review", "to review")),
    (TakeoffItem.ReviewState.ACCEPTED, ("accepted", "approved")),
    (TakeoffItem.ReviewState.REJECTED, ("rejected", "discarded")),
    (TakeoffItem.ReviewState.EDITED, ("edited", "adjusted")),
]


def _normalize_assembly_profile(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid assembly_profile.")
    normalized = value.strip().lower()
    if normalized not in SUPPORTED_ASSEMBLY_PROFILES:
        raise ValueError("Invalid assembly_profile.")
    return normalized


def _decimal_to_string(value: Decimal | None) -> str:
    if value is None:
        return "0.0000"
    if not isinstance(value, Decimal):
        try:
            value = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return "0.0000"
    if not value.is_finite():
        return "0.0000"
    return format(value.quantize(Decimal("0.0001")), "f")


def _default_category_unit_for_suggestion(label: str | None, suggestion_type: str | None) -> tuple[str, str]:
    """Derive default category and unit from suggestion label/type. Uses exact label match and
    word-boundary matching to avoid over-match (e.g. 'room' in 'bathroom')."""
    if label:
        label_lower = label.strip().lower()
        if label_lower in LABEL_TO_CATEGORY_UNIT:
            return LABEL_TO_CATEGORY_UNIT[label_lower]
        # Word-boundary match: key must appear as a whole word in label (e.g. "door" in "door 1", not "doorway")
        for key, (cat, unit) in LABEL_TO_CATEGORY_UNIT.items():
            if re.search(r"\b" + re.escape(key) + r"\b", label_lower):
                return cat, unit
    # Polygon/area -> square_feet; point -> count; rectangle -> count
    if suggestion_type == "polygon":
        return TakeoffItem.Category.CONCRETE_AREAS, TakeoffItem.Unit.SQUARE_FEET
    if suggestion_type == "polyline":
        return TakeoffItem.Category.LINEAR_MEASUREMENTS, TakeoffItem.Unit.LINEAR_FEET
    return TakeoffItem.Category.CUSTOM, TakeoffItem.Unit.COUNT


def _decimal_or_none(value: Any) -> Decimal | None:
    try:
        if value is None:
            return None
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _normalized_polygon_area(points: list[dict[str, Any]]) -> Decimal | None:
    if len(points) < 3:
        return None
    parsed: list[tuple[Decimal, Decimal]] = []
    for point in points:
        if not isinstance(point, dict):
            return None
        x = _decimal_or_none(point.get("x"))
        y = _decimal_or_none(point.get("y"))
        if x is None or y is None:
            return None
        parsed.append((x, y))
    area = Decimal("0")
    for i in range(len(parsed)):
        x1, y1 = parsed[i]
        x2, y2 = parsed[(i + 1) % len(parsed)]
        area += (x1 * y2) - (x2 * y1)
    return abs(area) / Decimal("2")


def _geometry_normalized_area(geometry_json: dict[str, Any]) -> Decimal | None:
    gtype = geometry_json.get("type")
    if gtype == "rectangle":
        width = _decimal_or_none(geometry_json.get("width"))
        height = _decimal_or_none(geometry_json.get("height"))
        if width is None or height is None:
            return None
        if width < 0 or height < 0:
            return None
        return width * height
    if gtype == "polygon":
        points = geometry_json.get("points")
        if not isinstance(points, list):
            return None
        return _normalized_polygon_area(points)
    return None


def _geometry_scaled_polyline_length_feet(
    geometry_json: dict[str, Any], sheet_width_feet: Decimal, sheet_height_feet: Decimal
) -> Decimal | None:
    gtype = geometry_json.get("type")
    if gtype != "polyline":
        return None
    points = geometry_json.get("points")
    if not isinstance(points, list) or len(points) < 2:
        return None

    parsed: list[tuple[Decimal, Decimal]] = []
    for point in points:
        if not isinstance(point, dict):
            return None
        x = _decimal_or_none(point.get("x"))
        y = _decimal_or_none(point.get("y"))
        if x is None or y is None:
            return None
        parsed.append((x, y))

    total = Decimal("0")
    for i in range(1, len(parsed)):
        x1, y1 = parsed[i - 1]
        x2, y2 = parsed[i]
        dx_feet = (x2 - x1) * sheet_width_feet
        dy_feet = (y2 - y1) * sheet_height_feet
        segment = math.sqrt(float(dx_feet * dx_feet + dy_feet * dy_feet))
        total += Decimal(str(segment))
    return total


def _calibrated_sheet_dimensions_feet(plan_sheet: PlanSheet) -> tuple[Decimal, Decimal] | None:
    width = _decimal_or_none(getattr(plan_sheet, "calibrated_width", None))
    height = _decimal_or_none(getattr(plan_sheet, "calibrated_height", None))
    if width is None or height is None:
        return None
    if width <= 0 or height <= 0:
        return None
    calibrated_unit = getattr(plan_sheet, "calibrated_unit", PlanSheet.CalibrationUnit.FEET)
    if calibrated_unit == PlanSheet.CalibrationUnit.METERS:
        meters_to_feet = Decimal("3.28084")
        width *= meters_to_feet
        height *= meters_to_feet
    return width, height


def _estimate_quantity_from_geometry(
    geometry_json: dict[str, Any] | None, unit: str, plan_sheet: PlanSheet
) -> Decimal:
    geometry = geometry_json if isinstance(geometry_json, dict) else {}

    # Provider-supplied explicit quantities take precedence.
    if unit == TakeoffItem.Unit.SQUARE_FEET:
        explicit = _decimal_or_none(geometry.get("area_sqft"))
        if explicit is not None and explicit >= 0:
            return explicit
        dims = _calibrated_sheet_dimensions_feet(plan_sheet)
        normalized_area = _geometry_normalized_area(geometry)
        if dims and normalized_area is not None:
            width_feet, height_feet = dims
            return normalized_area * width_feet * height_feet
        return Decimal("1")

    if unit == TakeoffItem.Unit.LINEAR_FEET:
        explicit = _decimal_or_none(geometry.get("length_lf"))
        if explicit is None:
            explicit = _decimal_or_none(geometry.get("length_linear_feet"))
        if explicit is not None and explicit >= 0:
            return explicit
        dims = _calibrated_sheet_dimensions_feet(plan_sheet)
        if dims:
            length = _geometry_scaled_polyline_length_feet(geometry, dims[0], dims[1])
            if length is not None:
                return length
            if geometry.get("type") == "rectangle":
                width = _decimal_or_none(geometry.get("width"))
                height = _decimal_or_none(geometry.get("height"))
                if width is not None and height is not None and width >= 0 and height >= 0:
                    return (width * dims[0]) + (height * dims[1])
        return Decimal("1")

    if unit == TakeoffItem.Unit.CUBIC_YARDS:
        explicit = _decimal_or_none(geometry.get("volume_cubic_yards"))
        if explicit is not None and explicit >= 0:
            return explicit
        return Decimal("1")

    # Count/each/custom default to one item per accepted suggestion.
    return Decimal("1")


def _round_up_to_step(quantity: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return quantity
    return (quantity / step).to_integral_value(rounding=ROUND_CEILING) * step


def _decimal_setting(setting_name: str, default: str) -> Decimal:
    raw = getattr(settings, setting_name, default)
    try:
        parsed = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)
    if not parsed.is_finite():
        return Decimal(default)
    return parsed


def _normalize_estimator_quantity(quantity: Decimal, unit: str) -> Decimal:
    if not quantity.is_finite():
        raise ValueError("Quantity must be a finite number.")
    if quantity < 0:
        raise ValueError("Quantity must be non-negative.")

    linear_waste = _decimal_setting("PRECONSTRUCTION_LINEAR_WASTE_FACTOR", "0")
    area_waste = _decimal_setting("PRECONSTRUCTION_AREA_WASTE_FACTOR", "0")
    linear_step = _decimal_setting("PRECONSTRUCTION_LINEAR_ROUND_STEP_FEET", "0.0001")
    area_step = _decimal_setting("PRECONSTRUCTION_AREA_ROUND_STEP_SQFT", "0.0001")
    cubic_step = _decimal_setting("PRECONSTRUCTION_CUBIC_ROUND_STEP_CY", "0.0001")

    if unit in {TakeoffItem.Unit.COUNT, TakeoffItem.Unit.EACH}:
        if quantity == 0:
            return Decimal("0")
        return quantity.to_integral_value(rounding=ROUND_CEILING)

    if unit == TakeoffItem.Unit.LINEAR_FEET:
        adjusted = quantity * (Decimal("1") + max(Decimal("0"), linear_waste))
        return _round_up_to_step(adjusted, linear_step)

    if unit == TakeoffItem.Unit.SQUARE_FEET:
        adjusted = quantity * (Decimal("1") + max(Decimal("0"), area_waste))
        return _round_up_to_step(adjusted, area_step)

    if unit == TakeoffItem.Unit.CUBIC_YARDS:
        return _round_up_to_step(quantity, cubic_step)

    return quantity


def _contains_any(text: str, keywords: tuple[str, ...] | list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _choice_label(choice_enum, value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(choice_enum(value).label)
    except ValueError:
        return value.replace("_", " ")


def _sheet_label(sheet: PlanSheet | None) -> str:
    if sheet is None:
        return ""
    return sheet.sheet_number or sheet.title or f"Sheet {str(sheet.id)[:8]}"


def _scope_label(project, plan_set: PlanSet | None, plan_sheet: PlanSheet | None) -> str:
    if plan_sheet is not None:
        return f"sheet {_sheet_label(plan_sheet)} in plan set {plan_sheet.plan_set.name}"
    if plan_set is not None:
        return f"plan set {plan_set.name}"
    return f"project {project.code} - {project.name}"


def _build_copilot_citation(kind: str, object_id: str, label: str, detail: str) -> dict[str, str]:
    return {
        "kind": kind,
        "id": object_id,
        "label": label,
        "detail": detail,
    }


def _format_timestamp(value) -> str:
    if value is None:
        return "unknown time"
    localized = timezone.localtime(value)
    return localized.strftime("%b %d, %Y %I:%M %p")


def _default_copilot_prompts(plan_set: PlanSet | None, plan_sheet: PlanSheet | None) -> list[str]:
    if plan_sheet is not None:
        sheet_name = _sheet_label(plan_sheet)
        return [
            f"How many pending takeoff items are on {sheet_name}?",
            f"Is {sheet_name} calibrated for quantity takeoff?",
            f"What was the latest AI analysis run on {sheet_name}?",
            "What is the latest snapshot status for this plan set?",
            "What do the uploaded project documents say about door hardware?",
        ]
    if plan_set is not None:
        return [
            "How many pending takeoff items are on this plan set?",
            "Which sheets in this plan set are calibrated?",
            "What is the latest snapshot status for this plan set?",
            "What was the last export created for this plan set?",
            "What do the uploaded project documents say about door hardware?",
        ]
    return [
        "List the plan sets for this project.",
        "How many takeoff items exist across this project?",
        "Which sheets are calibrated?",
        "What is the latest export created for this project?",
        "What do the uploaded project documents say about door hardware?",
    ]


def _copilot_scope_payload(project, plan_set: PlanSet | None, plan_sheet: PlanSheet | None) -> dict[str, str | None]:
    return {
        "project_id": str(project.id),
        "project_code": project.code,
        "project_name": project.name,
        "plan_set_id": str(plan_set.id) if plan_set else None,
        "plan_set_name": plan_set.name if plan_set else None,
        "plan_sheet_id": str(plan_sheet.id) if plan_sheet else None,
        "plan_sheet_name": _sheet_label(plan_sheet) if plan_sheet else None,
    }


def _build_copilot_result(
    *,
    status: str,
    answer: str,
    project,
    plan_set: PlanSet | None,
    plan_sheet: PlanSheet | None,
    citations: list[dict[str, str]],
    suggested_prompts: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "answer": answer,
        "scope": _copilot_scope_payload(project, plan_set, plan_sheet),
        "citations": citations,
        "suggested_prompts": suggested_prompts or _default_copilot_prompts(plan_set, plan_sheet),
    }


def _detect_requested_categories(question_lower: str) -> list[str]:
    matches: list[str] = []
    for category, keywords in COPILOT_CATEGORY_KEYWORDS:
        if _contains_any(question_lower, keywords):
            matches.append(category)
    return matches


def _detect_requested_review_state(question_lower: str) -> str | None:
    for review_state, keywords in COPILOT_REVIEW_KEYWORDS:
        if _contains_any(question_lower, keywords):
            return review_state
    return None


def _format_unit_totals(unit_totals: list[dict[str, Any]]) -> str:
    if not unit_totals:
        return "no measurable quantity yet"
    return ", ".join(
        f"{row['quantity_total']} {_choice_label(TakeoffItem.Unit, row['unit']).lower()}"
        for row in unit_totals
    )


def _detect_assembly_profile(category: str, label: str | None) -> str | None:
    if category == TakeoffItem.Category.DOORS:
        return ASSEMBLY_PROFILE_DOOR_SET
    if category == TakeoffItem.Category.WINDOWS:
        return ASSEMBLY_PROFILE_WINDOW_SET
    if category == TakeoffItem.Category.PLUMBING_FIXTURES:
        return ASSEMBLY_PROFILE_FIXTURE_SET
    if category != TakeoffItem.Category.CUSTOM:
        return None

    label_lower = (label or "").strip().lower()
    if re.search(r"\bdoor(s)?\b", label_lower):
        return ASSEMBLY_PROFILE_DOOR_SET
    if re.search(r"\bwindow(s)?\b", label_lower):
        return ASSEMBLY_PROFILE_WINDOW_SET
    if re.search(r"\b(toilet|lavatory|sink|fixture)\b", label_lower):
        return ASSEMBLY_PROFILE_FIXTURE_SET
    return None


def _expand_takeoff_components(
    *,
    category: str,
    unit: str,
    quantity: Decimal,
    label: str | None,
    assembly_profile: str,
) -> tuple[list[dict[str, Any]], str]:
    profile = _normalize_assembly_profile(assembly_profile)
    if profile == ASSEMBLY_PROFILE_AUTO:
        profile = _detect_assembly_profile(category, label) or ASSEMBLY_PROFILE_NONE

    components = [
        {
            "category": category,
            "unit": unit,
            "quantity": _normalize_estimator_quantity(quantity, unit),
            "notes_suffix": "Primary quantity",
        }
    ]

    if profile == ASSEMBLY_PROFILE_DOOR_SET:
        components.append(
            {
                "category": TakeoffItem.Category.DOOR_HARDWARE,
                "unit": TakeoffItem.Unit.EACH,
                "quantity": _normalize_estimator_quantity(quantity, TakeoffItem.Unit.EACH),
                "notes_suffix": "Door hardware set (auto assembly)",
            }
        )
    elif profile == ASSEMBLY_PROFILE_WINDOW_SET:
        # Window assemblies are represented by the primary line item only in v1.
        pass
    elif profile == ASSEMBLY_PROFILE_FIXTURE_SET:
        # Fixture assemblies are represented by the primary line item only in v1.
        pass

    return components, profile


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
    with transaction.atomic():
        suggestion = AISuggestion.objects.select_related("plan_sheet", "plan_sheet__plan_set", "analysis_run").select_for_update().get(
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

        # Derive category/unit from suggestion label when not provided (estimator workflow)
        if category is None or unit is None:
            default_cat, default_unit = _default_category_unit_for_suggestion(
                suggestion.label, suggestion.suggestion_type
            )
            if category is None:
                category = default_cat
            if unit is None:
                unit = default_unit
        allowed_categories = {choice for choice, _ in TakeoffItem.Category.choices}
        allowed_units = {choice for choice, _ in TakeoffItem.Unit.choices}
        if category not in allowed_categories:
            raise ValueError("Invalid category.")
        if unit not in allowed_units:
            raise ValueError("Invalid unit.")

        qty = quantity
        if qty is None:
            qty = _estimate_quantity_from_geometry(final_geometry, unit, plan_sheet)
        elif isinstance(qty, str):
            try:
                qty = Decimal(qty)
            except InvalidOperation:
                raise ValueError("Invalid quantity.")
        elif not isinstance(qty, Decimal):
            try:
                qty = Decimal(str(qty))
            except (InvalidOperation, TypeError, ValueError):
                raise ValueError("Invalid quantity.")
        if not isinstance(qty, Decimal):
            qty = Decimal(str(qty))

        assembly_profile = ASSEMBLY_PROFILE_AUTO
        components, resolved_profile = _expand_takeoff_components(
            category=category or TakeoffItem.Category.CUSTOM,
            unit=unit or TakeoffItem.Unit.COUNT,
            quantity=qty,
            label=final_label,
            assembly_profile=assembly_profile,
        )
        if not components:
            raise ValueError("No takeoff components were generated.")

        created_takeoffs: list[TakeoffItem] = []
        for component in components:
            notes_parts = [f"From suggestion: {final_label or suggestion.id}"]
            notes_suffix = component.get("notes_suffix")
            if isinstance(notes_suffix, str) and notes_suffix.strip():
                notes_parts.append(notes_suffix.strip())
            created_takeoffs.append(
                TakeoffItem.objects.create(
                    project_id=plan_sheet.project_id,
                    plan_set=plan_set,
                    plan_sheet=plan_sheet,
                    source_annotation=annotation,
                    category=component["category"],
                    unit=component["unit"],
                    quantity=component["quantity"],
                    notes=" | ".join(notes_parts),
                    source=TakeoffItem.Source.AI_ASSISTED,
                    review_state=TakeoffItem.ReviewState.EDITED if overrides_provided else TakeoffItem.ReviewState.ACCEPTED,
                    created_by=user,
                    updated_by=user,
                )
            )
        takeoff = created_takeoffs[0]
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
                {
                    "annotation_id": str(annotation.id),
                    "takeoff_id": str(takeoff.id),
                    "overrides": override_keys,
                    "assembly_profile": resolved_profile,
                    "component_count": len(created_takeoffs),
                },
            )
        else:
            _record(
                "accept_ai_suggestion",
                user,
                "AISuggestion",
                str(suggestion.id),
                project_id,
                {
                    "annotation_id": str(annotation.id),
                    "takeoff_id": str(takeoff.id),
                    "assembly_profile": resolved_profile,
                    "component_count": len(created_takeoffs),
                },
            )
        return annotation, takeoff


def create_takeoff_from_annotation(
    annotation_id: str,
    user,
    *,
    assembly_profile: str = ASSEMBLY_PROFILE_AUTO,
) -> tuple[TakeoffItem, list[TakeoffItem], str]:
    """Create one or more estimator takeoff rows from a chosen annotation."""
    assembly_profile = _normalize_assembly_profile(assembly_profile)

    with transaction.atomic():
        annotation = (
            AnnotationItem.objects.select_related("plan_sheet", "plan_sheet__plan_set")
            .select_for_update()
            .get(id=annotation_id)
        )
        if annotation.linked_takeoff_item_id:
            raise ValueError("Annotation already has a linked takeoff item.")

        plan_sheet = annotation.plan_sheet
        plan_set = plan_sheet.plan_set
        category, unit = _default_category_unit_for_suggestion(
            annotation.label,
            annotation.annotation_type,
        )
        estimated_quantity = _estimate_quantity_from_geometry(
            annotation.geometry_json if isinstance(annotation.geometry_json, dict) else {},
            unit,
            plan_sheet,
        )
        components, resolved_profile = _expand_takeoff_components(
            category=category,
            unit=unit,
            quantity=estimated_quantity,
            label=annotation.label,
            assembly_profile=assembly_profile,
        )
        if not components:
            raise ValueError("No takeoff components were generated.")

        created: list[TakeoffItem] = []
        for component in components:
            notes_parts = [f"From annotation: {annotation.label or annotation.id}"]
            notes_suffix = component.get("notes_suffix")
            if isinstance(notes_suffix, str) and notes_suffix.strip():
                notes_parts.append(notes_suffix.strip())
            created.append(
                TakeoffItem.objects.create(
                    project_id=plan_sheet.project_id,
                    plan_set=plan_set,
                    plan_sheet=plan_sheet,
                    source_annotation=annotation,
                    category=component["category"],
                    unit=component["unit"],
                    quantity=component["quantity"],
                    notes=" | ".join(notes_parts),
                    source=TakeoffItem.Source.MANUAL,
                    review_state=TakeoffItem.ReviewState.PENDING,
                    created_by=user,
                    updated_by=user,
                )
            )

        primary = created[0]
        annotation.linked_takeoff_item = primary
        annotation.save(update_fields=["linked_takeoff_item", "updated_at"])
        _record(
            "create_takeoff_from_annotation",
            user,
            "AnnotationItem",
            str(annotation.id),
            str(plan_sheet.project_id),
            {
                "takeoff_id": str(primary.id),
                "assembly_profile": resolved_profile,
                "component_count": len(created),
            },
        )
        return primary, created[1:], resolved_profile


def build_takeoff_summary(queryset) -> dict[str, Any]:
    """Aggregate takeoff rows into estimator-friendly review rollups."""
    zero_decimal = Value(Decimal("0"), output_field=DecimalField(max_digits=14, decimal_places=4))
    review_counts = {
        row["review_state"]: row["item_count"]
        for row in queryset.values("review_state").annotate(item_count=Count("id")).order_by("review_state")
    }
    source_counts = {
        row["source"]: row["item_count"]
        for row in queryset.values("source").annotate(item_count=Count("id")).order_by("source")
    }

    return {
        "total_items": queryset.count(),
        "pending_items": review_counts.get(TakeoffItem.ReviewState.PENDING, 0),
        "accepted_items": review_counts.get(TakeoffItem.ReviewState.ACCEPTED, 0),
        "rejected_items": review_counts.get(TakeoffItem.ReviewState.REJECTED, 0),
        "edited_items": review_counts.get(TakeoffItem.ReviewState.EDITED, 0),
        "manual_items": source_counts.get(TakeoffItem.Source.MANUAL, 0),
        "ai_assisted_items": source_counts.get(TakeoffItem.Source.AI_ASSISTED, 0),
        "linked_annotation_items": queryset.aggregate(
            count=Count(
                "id",
                filter=Q(source_annotation__isnull=False) | Q(linked_annotation__isnull=False),
            )
        )["count"]
        or 0,
        "unit_totals": [
            {
                "unit": row["unit"],
                "item_count": row["item_count"],
                "quantity_total": _decimal_to_string(row["quantity_total"]),
            }
            for row in queryset.values("unit")
            .annotate(item_count=Count("id"), quantity_total=Coalesce(Sum("quantity"), zero_decimal))
            .order_by("unit")
        ],
        "category_totals": [
            {
                "category": row["category"],
                "unit": row["unit"],
                "item_count": row["item_count"],
                "quantity_total": _decimal_to_string(row["quantity_total"]),
            }
            for row in queryset.values("category", "unit")
            .annotate(item_count=Count("id"), quantity_total=Coalesce(Sum("quantity"), zero_decimal))
            .order_by("category", "unit")
        ],
        "review_state_totals": [
            {"review_state": row["review_state"], "item_count": row["item_count"]}
            for row in queryset.values("review_state").annotate(item_count=Count("id")).order_by("review_state")
        ],
        "source_totals": [
            {"source": row["source"], "item_count": row["item_count"]}
            for row in queryset.values("source").annotate(item_count=Count("id")).order_by("source")
        ],
    }


def _answer_copilot_help(project, plan_set: PlanSet | None, plan_sheet: PlanSheet | None) -> dict[str, Any]:
    scope_label = _scope_label(project, plan_set, plan_sheet)
    answer = (
        f"I can answer grounded questions about {scope_label} using the live preconstruction record: "
        "plan sets, sheets, takeoff totals, AI analysis runs, snapshots, exports, and any parsed project documents "
        "uploaded for this project. If the needed document is not uploaded or did not parse, I will call that out "
        "instead of guessing."
    )
    citations = [
        _build_copilot_citation(
            "project",
            str(project.id),
            f"{project.code} - {project.name}",
            "Grounded scope includes plan sets, sheets, takeoff, AI runs, snapshots, exports, and parsed project documents.",
        )
    ]
    if plan_set is not None:
        citations.append(
            _build_copilot_citation(
                "plan_set",
                str(plan_set.id),
                plan_set.name,
                f"Scoped to plan set status {_choice_label(PlanSet.Status, plan_set.status).lower()}.",
            )
        )
    if plan_sheet is not None:
        citations.append(
            _build_copilot_citation(
                "plan_sheet",
                str(plan_sheet.id),
                _sheet_label(plan_sheet),
                f"Scoped to {plan_file_type_from_storage_key(plan_sheet.storage_key).upper()} sheet.",
            )
        )
    return _build_copilot_result(
        status="limited",
        answer=answer,
        project=project,
        plan_set=plan_set,
        plan_sheet=plan_sheet,
        citations=citations,
    )


def _answer_document_gap(project, plan_set: PlanSet | None, plan_sheet: PlanSheet | None) -> dict[str, Any]:
    scope_label = _scope_label(project, plan_set, plan_sheet)
    answer = (
        f"I cannot answer that from {scope_label} yet because I do not have parsed project documents in scope for "
        "specs, addenda, RFIs, submittals, or vendor material. The right sources for that question would be the "
        "project spec book, addenda log, RFI register, or submittal package once those documents are uploaded here."
    )
    citations = [
        _build_copilot_citation(
            "project",
            str(project.id),
            f"{project.code} - {project.name}",
            "No parsed project documents are currently available in scope.",
        )
    ]
    return _build_copilot_result(
        status="needs_documents",
        answer=answer,
        project=project,
        plan_set=plan_set,
        plan_sheet=plan_sheet,
        citations=citations,
    )


def _answer_document_question(project, plan_set: PlanSet | None, plan_sheet: PlanSheet | None, question: str) -> dict[str, Any]:
    scope_label = _scope_label(project, plan_set, plan_sheet)
    search_result = search_project_documents(project=project, plan_set=plan_set, question=question, limit=3)
    document_count = search_result["document_count"]
    matches = search_result["matches"]

    if document_count == 0:
        return _answer_document_gap(project, plan_set, plan_sheet)

    if not matches:
        answer = (
            f"I searched {document_count} parsed project document{'s' if document_count != 1 else ''} in "
            f"{scope_label} but did not find a strong match for that question yet."
        )
        citations = [
            _build_copilot_citation(
                "document_search",
                f"{project.id}:{plan_set.id if plan_set else 'all'}",
                "Project document search",
                f"Searched {document_count} parsed documents in scope with no strong match.",
            )
        ]
        return _build_copilot_result(
            status="grounded",
            answer=answer,
            project=project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            citations=citations,
        )

    summary_parts: list[str] = []
    citations: list[dict[str, str]] = []
    for match in matches:
        document: ProjectDocument = match["document"]
        chunk = match["chunk"]
        page_part = f", page {chunk.page_number}" if chunk.page_number else ""
        summary_parts.append(
            f"{document.title} ({_choice_label(ProjectDocument.DocumentType, document.document_type).lower()}{page_part}) "
            f"looks relevant: {match['snippet']}"
        )
        citations.append(
            _build_copilot_citation(
                "document",
                str(document.id),
                document.title,
                f"{_choice_label(ProjectDocument.DocumentType, document.document_type)}{page_part}: {match['snippet']}",
            )
        )

    answer = f"I found relevant project-document evidence in {scope_label}. " + " ".join(summary_parts)
    return _build_copilot_result(
        status="grounded",
        answer=answer,
        project=project,
        plan_set=plan_set,
        plan_sheet=plan_sheet,
        citations=citations,
    )


def _answer_plan_set_question(project, plan_sets, plan_set: PlanSet | None, plan_sheet: PlanSheet | None) -> dict[str, Any]:
    if plan_set is not None:
        sheet_count = plan_set.sheets.count()
        answer = (
            f"{plan_set.name} is currently {_choice_label(PlanSet.Status, plan_set.status).lower()} and has "
            f"{sheet_count} sheet{'s' if sheet_count != 1 else ''}."
        )
        citations = [
            _build_copilot_citation(
                "plan_set",
                str(plan_set.id),
                plan_set.name,
                f"Status {_choice_label(PlanSet.Status, plan_set.status).lower()}, {sheet_count} sheets.",
            )
        ]
        return _build_copilot_result(
            status="grounded",
            answer=answer,
            project=project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            citations=citations,
        )

    total = plan_sets.count()
    if total == 0:
        answer = f"I do not have any plan sets yet for project {project.code} - {project.name}."
        citations = [
            _build_copilot_citation(
                "project",
                str(project.id),
                f"{project.code} - {project.name}",
                "No plan sets exist yet.",
            )
        ]
        return _build_copilot_result(
            status="grounded",
            answer=answer,
            project=project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            citations=citations,
        )

    listed_sets = list(plan_sets[:5])
    details = ", ".join(
        f"{item.name} ({_choice_label(PlanSet.Status, item.status).lower()}, {item.sheets.count()} sheets)"
        for item in listed_sets
    )
    answer = f"This project has {total} plan set{'s' if total != 1 else ''}: {details}."
    citations = [
        _build_copilot_citation(
            "plan_set",
            str(item.id),
            item.name,
            f"Status {_choice_label(PlanSet.Status, item.status).lower()}, {item.sheets.count()} sheets.",
        )
        for item in listed_sets
    ]
    return _build_copilot_result(
        status="grounded",
        answer=answer,
        project=project,
        plan_set=plan_set,
        plan_sheet=plan_sheet,
        citations=citations,
    )


def _answer_sheet_question(project, sheets, plan_set: PlanSet | None, plan_sheet: PlanSheet | None, question_lower: str) -> dict[str, Any]:
    sheet_count = sheets.count()
    scope_label = _scope_label(project, plan_set, plan_sheet)
    if sheet_count == 0:
        answer = f"I do not have any sheets in {scope_label} yet."
        citations = [
            _build_copilot_citation(
                "project",
                str(project.id),
                f"{project.code} - {project.name}",
                f"No sheets found in {scope_label}.",
            )
        ]
        return _build_copilot_result(
            status="grounded",
            answer=answer,
            project=project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            citations=citations,
        )

    if "calibrat" in question_lower or "scale" in question_lower:
        calibrated_sheets = [
            sheet for sheet in sheets if sheet.calibrated_width is not None and sheet.calibrated_height is not None
        ]
        if plan_sheet is not None:
            if calibrated_sheets:
                sheet = calibrated_sheets[0]
                answer = (
                    f"{_sheet_label(sheet)} is calibrated at {sheet.calibrated_width} by {sheet.calibrated_height} "
                    f"{sheet.calibrated_unit}."
                )
            else:
                answer = f"{_sheet_label(plan_sheet)} is not calibrated yet."
            citations = [
                _build_copilot_citation(
                    "plan_sheet",
                    str(plan_sheet.id),
                    _sheet_label(plan_sheet),
                    "Calibration present." if calibrated_sheets else "No calibration values stored.",
                )
            ]
        else:
            answer = (
                f"{len(calibrated_sheets)} of {sheet_count} sheet{'s' if sheet_count != 1 else ''} in {scope_label} "
                "currently have calibration values."
            )
            citations = [
                _build_copilot_citation(
                    "plan_sheet",
                    str(sheet.id),
                    _sheet_label(sheet),
                    f"Calibrated at {sheet.calibrated_width} x {sheet.calibrated_height} {sheet.calibrated_unit}.",
                )
                for sheet in calibrated_sheets[:5]
            ]
        return _build_copilot_result(
            status="grounded",
            answer=answer,
            project=project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            citations=citations,
        )

    listed_sheets = list(sheets[:5])
    details = ", ".join(
        f"{_sheet_label(sheet)} ({plan_file_type_from_storage_key(sheet.storage_key).upper()}, {sheet.parse_status})"
        for sheet in listed_sheets
    )
    answer = f"I found {sheet_count} sheet{'s' if sheet_count != 1 else ''} in {scope_label}: {details}."
    citations = [
        _build_copilot_citation(
            "plan_sheet",
            str(sheet.id),
            _sheet_label(sheet),
            f"{plan_file_type_from_storage_key(sheet.storage_key).upper()} sheet, parse status {sheet.parse_status}.",
        )
        for sheet in listed_sheets
    ]
    return _build_copilot_result(
        status="grounded",
        answer=answer,
        project=project,
        plan_set=plan_set,
        plan_sheet=plan_sheet,
        citations=citations,
    )


def _answer_filetype_question(project, sheets, plan_set: PlanSet | None, plan_sheet: PlanSheet | None) -> dict[str, Any]:
    file_counts = {"pdf": 0, "dxf": 0, "dwg": 0, "unknown": 0}
    for sheet in sheets:
        file_type = plan_file_type_from_storage_key(sheet.storage_key)
        file_counts[file_type if file_type in file_counts else "unknown"] += 1

    cad_count = file_counts["dxf"] + file_counts["dwg"]
    scope_label = _scope_label(project, plan_set, plan_sheet)
    answer = (
        f"In {scope_label}, I see {file_counts['pdf']} PDF sheet{'s' if file_counts['pdf'] != 1 else ''}, "
        f"{file_counts['dxf']} DXF sheet{'s' if file_counts['dxf'] != 1 else ''}, and "
        f"{file_counts['dwg']} DWG sheet{'s' if file_counts['dwg'] != 1 else ''}. "
        f"That gives you {cad_count} CAD-native sheet{'s' if cad_count != 1 else ''} in scope."
    )
    citations = [
        _build_copilot_citation(
            "file_types",
            f"{project.id}:{plan_set.id if plan_set else 'all'}:{plan_sheet.id if plan_sheet else 'all'}",
            "Sheet file types",
            f"PDF {file_counts['pdf']}, DXF {file_counts['dxf']}, DWG {file_counts['dwg']}, unknown {file_counts['unknown']}.",
        )
    ]
    return _build_copilot_result(
        status="grounded",
        answer=answer,
        project=project,
        plan_set=plan_set,
        plan_sheet=plan_sheet,
        citations=citations,
    )


def _answer_takeoff_question(project, takeoffs, plan_set: PlanSet | None, plan_sheet: PlanSheet | None, question_lower: str) -> dict[str, Any]:
    requested_categories = _detect_requested_categories(question_lower)
    requested_review_state = _detect_requested_review_state(question_lower)
    filtered_takeoffs = takeoffs
    if requested_categories:
        filtered_takeoffs = filtered_takeoffs.filter(category__in=requested_categories)
    if requested_review_state:
        filtered_takeoffs = filtered_takeoffs.filter(review_state=requested_review_state)

    summary = build_takeoff_summary(filtered_takeoffs)
    scope_label = _scope_label(project, plan_set, plan_sheet)
    category_label = ", ".join(_choice_label(TakeoffItem.Category, value).lower() for value in requested_categories)
    review_label = _choice_label(TakeoffItem.ReviewState, requested_review_state).lower() if requested_review_state else ""
    filter_parts = [part for part in (review_label, category_label) if part]
    filter_label = " ".join(filter_parts).strip()

    if summary["total_items"] == 0:
        answer = f"I did not find any {filter_label + ' ' if filter_label else ''}takeoff items in {scope_label} yet."
        citations = [
            _build_copilot_citation(
                "takeoff_summary",
                f"{project.id}:{plan_set.id if plan_set else 'all'}:{plan_sheet.id if plan_sheet else 'all'}",
                "Takeoff summary",
                "No matching takeoff rows.",
            )
        ]
        return _build_copilot_result(
            status="grounded",
            answer=answer,
            project=project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            citations=citations,
        )

    quantity_text = _format_unit_totals(summary["unit_totals"])
    answer = (
        f"In {scope_label}, I found {summary['total_items']} {filter_label + ' ' if filter_label else ''}takeoff "
        f"row{'s' if summary['total_items'] != 1 else ''} totaling {quantity_text}. "
        f"{summary['pending_items']} pending, {summary['accepted_items']} accepted, "
        f"{summary['edited_items']} edited, and {summary['rejected_items']} rejected."
    )
    top_categories = sorted(
        summary["category_totals"],
        key=lambda row: (-row["item_count"], row["category"], row["unit"]),
    )[:3]
    if top_categories and not requested_categories:
        category_breakdown = ", ".join(
            f"{_choice_label(TakeoffItem.Category, row['category']).lower()} {row['quantity_total']} "
            f"{_choice_label(TakeoffItem.Unit, row['unit']).lower()}"
            for row in top_categories
        )
        answer += f" Largest categories in scope are {category_breakdown}."

    citations = [
        _build_copilot_citation(
            "takeoff_summary",
            f"{project.id}:{plan_set.id if plan_set else 'all'}:{plan_sheet.id if plan_sheet else 'all'}",
            "Takeoff summary",
            f"{summary['total_items']} rows, {summary['pending_items']} pending, {summary['accepted_items']} accepted.",
        )
    ]
    citations.extend(
        _build_copilot_citation(
            "takeoff_category",
            row["category"],
            _choice_label(TakeoffItem.Category, row["category"]),
            f"{row['quantity_total']} {_choice_label(TakeoffItem.Unit, row['unit']).lower()} across {row['item_count']} rows.",
        )
        for row in top_categories
    )
    return _build_copilot_result(
        status="grounded",
        answer=answer,
        project=project,
        plan_set=plan_set,
        plan_sheet=plan_sheet,
        citations=citations,
    )


def _answer_analysis_question(project, runs, suggestions, plan_set: PlanSet | None, plan_sheet: PlanSheet | None) -> dict[str, Any]:
    scope_label = _scope_label(project, plan_set, plan_sheet)
    run_count = runs.count()
    if run_count == 0:
        answer = f"I do not have any AI analysis runs in {scope_label} yet."
        citations = [
            _build_copilot_citation(
                "analysis",
                f"{project.id}:{plan_set.id if plan_set else 'all'}:{plan_sheet.id if plan_sheet else 'all'}",
                "AI analysis",
                "No analysis runs found in scope.",
            )
        ]
        return _build_copilot_result(
            status="grounded",
            answer=answer,
            project=project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            citations=citations,
        )

    latest_run = runs.first()
    suggestion_counts = {
        row["decision_state"]: row["item_count"]
        for row in suggestions.values("decision_state").annotate(item_count=Count("id")).order_by("decision_state")
    }
    answer = (
        f"I found {run_count} AI analysis run{'s' if run_count != 1 else ''} in {scope_label}. "
        f"The latest run used provider {latest_run.provider_name} on {_sheet_label(latest_run.plan_sheet)} and "
        f"finished with status {_choice_label(AIAnalysisRun.Status, latest_run.status).lower()} at "
        f"{_format_timestamp(latest_run.completed_at or latest_run.updated_at)}. "
        f"Suggestion decisions in scope: {suggestion_counts.get(AISuggestion.DecisionState.PENDING, 0)} pending, "
        f"{suggestion_counts.get(AISuggestion.DecisionState.ACCEPTED, 0)} accepted, "
        f"{suggestion_counts.get(AISuggestion.DecisionState.EDITED, 0)} edited, and "
        f"{suggestion_counts.get(AISuggestion.DecisionState.REJECTED, 0)} rejected."
    )
    citations = [
        _build_copilot_citation(
            "analysis_run",
            str(latest_run.id),
            f"{latest_run.provider_name} on {_sheet_label(latest_run.plan_sheet)}",
            f"Status {_choice_label(AIAnalysisRun.Status, latest_run.status).lower()} at {_format_timestamp(latest_run.completed_at or latest_run.updated_at)}.",
        ),
        _build_copilot_citation(
            "suggestions",
            f"{project.id}:{plan_set.id if plan_set else 'all'}:{plan_sheet.id if plan_sheet else 'all'}",
            "Suggestion decisions",
            f"Pending {suggestion_counts.get(AISuggestion.DecisionState.PENDING, 0)}, accepted {suggestion_counts.get(AISuggestion.DecisionState.ACCEPTED, 0)}, edited {suggestion_counts.get(AISuggestion.DecisionState.EDITED, 0)}, rejected {suggestion_counts.get(AISuggestion.DecisionState.REJECTED, 0)}.",
        ),
    ]
    return _build_copilot_result(
        status="grounded",
        answer=answer,
        project=project,
        plan_set=plan_set,
        plan_sheet=plan_sheet,
        citations=citations,
    )


def _answer_snapshot_question(project, snapshots, plan_set: PlanSet | None, plan_sheet: PlanSheet | None, question_lower: str) -> dict[str, Any]:
    scope_label = _scope_label(project, plan_set, plan_sheet)
    snapshot_count = snapshots.count()
    if snapshot_count == 0:
        answer = f"I do not have any revision snapshots in {scope_label} yet."
        citations = [
            _build_copilot_citation(
                "snapshots",
                f"{project.id}:{plan_set.id if plan_set else 'all'}",
                "Revision snapshots",
                "No snapshots found in scope.",
            )
        ]
        return _build_copilot_result(
            status="grounded",
            answer=answer,
            project=project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            citations=citations,
        )

    latest_snapshot = snapshots.first()
    status_counts = {
        row["status"]: row["item_count"]
        for row in snapshots.values("status").annotate(item_count=Count("id")).order_by("status")
    }
    answer = (
        f"I found {snapshot_count} revision snapshot{'s' if snapshot_count != 1 else ''} in {scope_label}. "
        f"The latest is {latest_snapshot.name} with status {_choice_label(RevisionSnapshot.Status, latest_snapshot.status).lower()} "
        f"created at {_format_timestamp(latest_snapshot.created_at)}."
    )
    if _contains_any(question_lower, ("compare", "changed", "difference")):
        answer += " I can report snapshot presence and status now, but structured revision diffing is still a later phase."
        status = "limited"
    else:
        answer += (
            f" Snapshot status counts in scope are draft {status_counts.get(RevisionSnapshot.Status.DRAFT, 0)}, "
            f"submitted {status_counts.get(RevisionSnapshot.Status.SUBMITTED, 0)}, approved {status_counts.get(RevisionSnapshot.Status.APPROVED, 0)}, "
            f"and locked {status_counts.get(RevisionSnapshot.Status.LOCKED, 0)}."
        )
        status = "grounded"

    citations = [
        _build_copilot_citation(
            "snapshot",
            str(latest_snapshot.id),
            latest_snapshot.name,
            f"Status {_choice_label(RevisionSnapshot.Status, latest_snapshot.status).lower()} created at {_format_timestamp(latest_snapshot.created_at)}.",
        )
    ]
    return _build_copilot_result(
        status=status,
        answer=answer,
        project=project,
        plan_set=plan_set,
        plan_sheet=plan_sheet,
        citations=citations,
    )


def _answer_export_question(project, exports, plan_set: PlanSet | None, plan_sheet: PlanSheet | None) -> dict[str, Any]:
    scope_label = _scope_label(project, plan_set, plan_sheet)
    export_count = exports.count()
    if export_count == 0:
        answer = f"I do not have any exports in {scope_label} yet."
        citations = [
            _build_copilot_citation(
                "exports",
                f"{project.id}:{plan_set.id if plan_set else 'all'}",
                "Exports",
                "No exports found in scope.",
            )
        ]
        return _build_copilot_result(
            status="grounded",
            answer=answer,
            project=project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            citations=citations,
        )

    latest_export = exports.first()
    answer = (
        f"I found {export_count} export{'s' if export_count != 1 else ''} in {scope_label}. "
        f"The latest export is {_choice_label(ExportRecord.ExportType, latest_export.export_type).lower()} with status "
        f"{_choice_label(ExportRecord.Status, latest_export.status).lower()} created at {_format_timestamp(latest_export.created_at)}."
    )
    citations = [
        _build_copilot_citation(
            "export",
            str(latest_export.id),
            _choice_label(ExportRecord.ExportType, latest_export.export_type),
            f"Status {_choice_label(ExportRecord.Status, latest_export.status).lower()} created at {_format_timestamp(latest_export.created_at)}.",
        )
    ]
    if latest_export.revision_snapshot_id:
        citations.append(
            _build_copilot_citation(
                "snapshot",
                str(latest_export.revision_snapshot_id),
                latest_export.revision_snapshot.name if latest_export.revision_snapshot else "Linked snapshot",
                "Export references a revision snapshot.",
            )
        )
    return _build_copilot_result(
        status="grounded",
        answer=answer,
        project=project,
        plan_set=plan_set,
        plan_sheet=plan_sheet,
        citations=citations,
    )


def _answer_general_summary(
    project,
    plan_sets,
    sheets,
    takeoffs,
    snapshots,
    exports,
    plan_set: PlanSet | None,
    plan_sheet: PlanSheet | None,
) -> dict[str, Any]:
    takeoff_summary = build_takeoff_summary(takeoffs)
    scope_label = _scope_label(project, plan_set, plan_sheet)
    answer = (
        f"For {scope_label}, I currently see {plan_sets.count()} plan set{'s' if plan_sets.count() != 1 else ''}, "
        f"{sheets.count()} sheet{'s' if sheets.count() != 1 else ''}, and {takeoff_summary['total_items']} takeoff row{'s' if takeoff_summary['total_items'] != 1 else ''}. "
        f"Takeoff review is {takeoff_summary['pending_items']} pending, {takeoff_summary['accepted_items']} accepted, "
        f"{takeoff_summary['edited_items']} edited, and {takeoff_summary['rejected_items']} rejected."
    )
    latest_snapshot = snapshots.first()
    latest_export = exports.first()
    if latest_snapshot is not None:
        answer += (
            f" Latest snapshot: {latest_snapshot.name} "
            f"({_choice_label(RevisionSnapshot.Status, latest_snapshot.status).lower()})."
        )
    if latest_export is not None:
        answer += (
            f" Latest export: {_choice_label(ExportRecord.ExportType, latest_export.export_type).lower()} "
            f"({_choice_label(ExportRecord.Status, latest_export.status).lower()})."
        )

    citations = [
        _build_copilot_citation(
            "project",
            str(project.id),
            f"{project.code} - {project.name}",
            f"{plan_sets.count()} plan sets, {sheets.count()} sheets, {takeoff_summary['total_items']} takeoff rows in scope.",
        ),
        _build_copilot_citation(
            "takeoff_summary",
            f"{project.id}:{plan_set.id if plan_set else 'all'}:{plan_sheet.id if plan_sheet else 'all'}",
            "Takeoff summary",
            f"Pending {takeoff_summary['pending_items']}, accepted {takeoff_summary['accepted_items']}, edited {takeoff_summary['edited_items']}, rejected {takeoff_summary['rejected_items']}.",
        ),
    ]
    if latest_snapshot is not None:
        citations.append(
            _build_copilot_citation(
                "snapshot",
                str(latest_snapshot.id),
                latest_snapshot.name,
                f"Status {_choice_label(RevisionSnapshot.Status, latest_snapshot.status).lower()}.",
            )
        )
    if latest_export is not None:
        citations.append(
            _build_copilot_citation(
                "export",
                str(latest_export.id),
                _choice_label(ExportRecord.ExportType, latest_export.export_type),
                f"Status {_choice_label(ExportRecord.Status, latest_export.status).lower()}.",
            )
        )
    return _build_copilot_result(
        status="grounded",
        answer=answer,
        project=project,
        plan_set=plan_set,
        plan_sheet=plan_sheet,
        citations=citations,
    )


def answer_preconstruction_question(
    *,
    project,
    question: str,
    plan_set: PlanSet | None = None,
    plan_sheet: PlanSheet | None = None,
) -> dict[str, Any]:
    if plan_sheet is not None and plan_set is None:
        plan_set = plan_sheet.plan_set

    question_text = (question or "").strip()
    if not question_text:
        raise ValueError("Question is required.")

    question_lower = question_text.lower()
    project_plan_sets = PlanSet.objects.filter(project=project).order_by("-created_at")
    scoped_plan_sets = project_plan_sets.filter(id=plan_set.id) if plan_set is not None else project_plan_sets

    scoped_sheets = PlanSheet.objects.filter(project=project).order_by("sheet_index", "created_at")
    if plan_set is not None:
        scoped_sheets = scoped_sheets.filter(plan_set=plan_set)
    if plan_sheet is not None:
        scoped_sheets = scoped_sheets.filter(id=plan_sheet.id)

    scoped_takeoffs = TakeoffItem.objects.filter(project=project)
    if plan_set is not None:
        scoped_takeoffs = scoped_takeoffs.filter(plan_set=plan_set)
    if plan_sheet is not None:
        scoped_takeoffs = scoped_takeoffs.filter(plan_sheet=plan_sheet)

    scoped_runs = AIAnalysisRun.objects.filter(project=project).select_related("plan_sheet").order_by("-created_at")
    if plan_set is not None:
        scoped_runs = scoped_runs.filter(plan_set=plan_set)
    if plan_sheet is not None:
        scoped_runs = scoped_runs.filter(plan_sheet=plan_sheet)

    scoped_suggestions = AISuggestion.objects.filter(project=project)
    if plan_set is not None:
        scoped_suggestions = scoped_suggestions.filter(analysis_run__plan_set=plan_set)
    if plan_sheet is not None:
        scoped_suggestions = scoped_suggestions.filter(plan_sheet=plan_sheet)

    scoped_snapshots = RevisionSnapshot.objects.filter(project=project).order_by("-created_at")
    if plan_set is not None:
        scoped_snapshots = scoped_snapshots.filter(plan_set=plan_set)

    scoped_exports = ExportRecord.objects.filter(project=project).select_related("revision_snapshot").order_by("-created_at")
    if plan_set is not None:
        scoped_exports = scoped_exports.filter(plan_set=plan_set)

    if _contains_any(question_lower, COPILOT_DOCUMENT_KEYWORDS) or _contains_any(question_lower, COPILOT_DOCUMENT_INTENT_KEYWORDS):
        return _answer_document_question(project, plan_set, plan_sheet, question_text)
    if _contains_any(question_lower, COPILOT_HELP_KEYWORDS):
        return _answer_copilot_help(project, plan_set, plan_sheet)
    if _contains_any(question_lower, COPILOT_TAKEOFF_KEYWORDS):
        return _answer_takeoff_question(project, scoped_takeoffs, plan_set, plan_sheet, question_lower)
    if _contains_any(question_lower, COPILOT_FILETYPE_KEYWORDS):
        return _answer_filetype_question(project, scoped_sheets, plan_set, plan_sheet)
    if _contains_any(question_lower, COPILOT_SNAPSHOT_KEYWORDS):
        return _answer_snapshot_question(project, scoped_snapshots, plan_set, plan_sheet, question_lower)
    if _contains_any(question_lower, COPILOT_EXPORT_KEYWORDS):
        return _answer_export_question(project, scoped_exports, plan_set, plan_sheet)
    if _contains_any(question_lower, COPILOT_ANALYSIS_KEYWORDS):
        return _answer_analysis_question(project, scoped_runs, scoped_suggestions, plan_set, plan_sheet)
    if _detect_requested_categories(question_lower):
        return _answer_takeoff_question(project, scoped_takeoffs, plan_set, plan_sheet, question_lower)
    if _contains_any(question_lower, COPILOT_SHEET_KEYWORDS):
        return _answer_sheet_question(project, scoped_sheets, plan_set, plan_sheet, question_lower)
    if _contains_any(question_lower, COPILOT_PLAN_SET_KEYWORDS):
        return _answer_plan_set_question(project, scoped_plan_sets, plan_set, plan_sheet)
    return _answer_general_summary(
        project,
        scoped_plan_sets,
        scoped_sheets,
        scoped_takeoffs,
        scoped_snapshots,
        scoped_exports,
        plan_set,
        plan_sheet,
    )


def run_plan_analysis(
    plan_sheet: PlanSheet, user_prompt: str, user, provider_name: str | None = None
) -> AIAnalysisRun:
    """Create AIAnalysisRun, run provider, create AISuggestion rows, record audit."""
    selected_provider = provider_name or settings.PRECONSTRUCTION_ANALYSIS_PROVIDER or "mock"
    with transaction.atomic():
        run = AIAnalysisRun.objects.create(
            project=plan_sheet.project,
            plan_set=plan_sheet.plan_set,
            plan_sheet=plan_sheet,
            provider_name=selected_provider,
            user_prompt=user_prompt or "",
            status=AIAnalysisRun.Status.RUNNING,
            request_payload_json={
                "user_prompt": user_prompt,
                "plan_sheet_id": str(plan_sheet.id),
                "provider_name": selected_provider,
            },
            started_at=timezone.now(),
            created_by=user,
        )
        try:
            provider = get_provider(selected_provider)
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


def batch_accept_suggestions(
    plan_sheet_id: str,
    user,
    *,
    min_confidence: float = 0.85,
) -> list[tuple[AnnotationItem, TakeoffItem]]:
    """
    Accept all pending suggestions on a plan sheet with confidence >= min_confidence.
    Returns list of (annotation, takeoff) for each accepted suggestion.
    All accepts are committed in a single transaction; on first failure the whole batch rolls back.
    """
    qs = AISuggestion.objects.filter(
        plan_sheet_id=plan_sheet_id,
        decision_state=AISuggestion.DecisionState.PENDING,
    ).select_related("plan_sheet", "plan_sheet__plan_set", "analysis_run")

    results: list[tuple[AnnotationItem, TakeoffItem]] = []
    with transaction.atomic():
        for s in qs:
            conf = s.confidence
            if conf is None:
                continue
            try:
                conf_val = float(conf)
            except (TypeError, ValueError):
                continue
            if conf_val >= min_confidence:
                ann, takeoff = accept_suggestion(str(s.id), user)
                results.append((ann, takeoff))
    return results


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
            "calibrated_width": str(sheet.calibrated_width) if sheet.calibrated_width is not None else None,
            "calibrated_height": str(sheet.calibrated_height) if sheet.calibrated_height is not None else None,
            "calibrated_unit": sheet.calibrated_unit,
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
