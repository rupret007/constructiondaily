"""DXF-based CAD analysis provider (entity extraction, no vision model required)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from preconstruction.filetypes import plan_file_type_from_storage_key
from preconstruction.storage import get_plan_file_path

from .base import BaseAnalysisProvider

_STOPWORDS = {
    "all",
    "and",
    "count",
    "find",
    "highlight",
    "identify",
    "mark",
    "of",
    "the",
    "to",
}


def _first_float(values: list[str] | None) -> float | None:
    if not values:
        return None
    for value in values:
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _to_int(value: str | None, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clamp_norm(value: float) -> float:
    return max(0.0, min(1.0, value))


def _entity_layer(data: dict[str, list[str]]) -> str:
    layer_values = data.get("8")
    if layer_values:
        layer = str(layer_values[0]).strip()
        if layer:
            return layer
    return "CAD"


def _iter_dxf_pairs(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    pairs: list[tuple[str, str]] = []
    i = 0
    while i + 1 < len(lines):
        code = lines[i].strip()
        value = lines[i + 1].strip()
        if code:
            pairs.append((code, value))
        i += 2
    return pairs


def _extract_entity_blocks(pairs: list[tuple[str, str]]) -> list[tuple[str, dict[str, list[str]]]]:
    entities: list[tuple[str, dict[str, list[str]]]] = []
    in_entities = False
    i = 0
    while i < len(pairs):
        code, value = pairs[i]
        upper_value = value.upper()
        if code == "0" and upper_value == "SECTION":
            if i + 1 < len(pairs):
                next_code, next_value = pairs[i + 1]
                if next_code == "2" and next_value.upper() == "ENTITIES":
                    in_entities = True
                    i += 2
                    continue
        if in_entities and code == "0" and upper_value == "ENDSEC":
            in_entities = False
            i += 1
            continue
        if not in_entities:
            i += 1
            continue
        if code == "0":
            entity_type = upper_value
            i += 1
            data: dict[str, list[str]] = {}
            while i < len(pairs):
                c, v = pairs[i]
                if c == "0":
                    break
                data.setdefault(c, []).append(v)
                i += 1
            entities.append((entity_type, data))
            continue
        i += 1
    return entities


@dataclass(slots=True)
class _CadShape:
    suggestion_type: str
    points: list[tuple[float, float]]
    label: str
    rationale: str
    layer: str
    confidence: float


def _lwpolyline_points(data: dict[str, list[str]]) -> list[tuple[float, float]]:
    xs = data.get("10", [])
    ys = data.get("20", [])
    count = min(len(xs), len(ys))
    points: list[tuple[float, float]] = []
    for idx in range(count):
        try:
            points.append((float(xs[idx]), float(ys[idx])))
        except (TypeError, ValueError):
            continue
    return points


def _sample_arc_points(
    center_x: float,
    center_y: float,
    radius: float,
    start_angle_deg: float,
    end_angle_deg: float,
    *,
    steps: int,
) -> list[tuple[float, float]]:
    if steps < 2:
        steps = 2
    start = math.radians(start_angle_deg)
    end = math.radians(end_angle_deg)
    if end < start:
        end += math.tau
    sweep = end - start
    points: list[tuple[float, float]] = []
    for idx in range(steps + 1):
        t = idx / steps
        angle = start + sweep * t
        points.append((center_x + (radius * math.cos(angle)), center_y + (radius * math.sin(angle))))
    return points


def _extract_shapes(entities: list[tuple[str, dict[str, list[str]]]]) -> list[_CadShape]:
    shapes: list[_CadShape] = []
    for entity_type, data in entities:
        layer = _entity_layer(data)
        label_hint = layer
        if entity_type == "LINE":
            x1 = _first_float(data.get("10"))
            y1 = _first_float(data.get("20"))
            x2 = _first_float(data.get("11"))
            y2 = _first_float(data.get("21"))
            if None in {x1, y1, x2, y2}:
                continue
            shapes.append(
                _CadShape(
                    suggestion_type="polyline",
                    points=[(x1, y1), (x2, y2)],
                    label=f"{label_hint} line".strip(),
                    rationale=f"Extracted LINE entity from layer '{layer}'.",
                    layer=layer,
                    confidence=0.9,
                )
            )
            continue

        if entity_type == "LWPOLYLINE":
            points = _lwpolyline_points(data)
            if len(points) < 2:
                continue
            closed = _to_int((data.get("70") or [None])[0], default=0) & 1
            suggestion_type = "polygon" if closed and len(points) >= 3 else "polyline"
            if suggestion_type == "polygon" and points[0] != points[-1]:
                points = points + [points[0]]
            shapes.append(
                _CadShape(
                    suggestion_type=suggestion_type,
                    points=points,
                    label=f"{label_hint} {suggestion_type}".strip(),
                    rationale=f"Extracted LWPOLYLINE entity from layer '{layer}'.",
                    layer=layer,
                    confidence=0.93,
                )
            )
            continue

        if entity_type == "CIRCLE":
            cx = _first_float(data.get("10"))
            cy = _first_float(data.get("20"))
            radius = _first_float(data.get("40"))
            if None in {cx, cy, radius} or radius is None or radius <= 0:
                continue
            points = _sample_arc_points(cx, cy, radius, 0.0, 360.0, steps=16)
            shapes.append(
                _CadShape(
                    suggestion_type="polygon",
                    points=points,
                    label=f"{label_hint} circle".strip(),
                    rationale=f"Extracted CIRCLE entity from layer '{layer}'.",
                    layer=layer,
                    confidence=0.88,
                )
            )
            continue

        if entity_type == "ARC":
            cx = _first_float(data.get("10"))
            cy = _first_float(data.get("20"))
            radius = _first_float(data.get("40"))
            start = _first_float(data.get("50"))
            end = _first_float(data.get("51"))
            if None in {cx, cy, radius, start, end}:
                continue
            if radius is None or radius <= 0:
                continue
            points = _sample_arc_points(cx, cy, radius, start, end, steps=12)
            shapes.append(
                _CadShape(
                    suggestion_type="polyline",
                    points=points,
                    label=f"{label_hint} arc".strip(),
                    rationale=f"Extracted ARC entity from layer '{layer}'.",
                    layer=layer,
                    confidence=0.86,
                )
            )
            continue

        if entity_type == "INSERT":
            x = _first_float(data.get("10"))
            y = _first_float(data.get("20"))
            if None in {x, y}:
                continue
            block_name = (data.get("2") or ["block"])[0]
            shapes.append(
                _CadShape(
                    suggestion_type="point",
                    points=[(x, y)],
                    label=f"{block_name}".strip() or "block",
                    rationale=f"Extracted INSERT block '{block_name}' from layer '{layer}'.",
                    layer=layer,
                    confidence=0.95,
                )
            )
            continue

        if entity_type in {"TEXT", "MTEXT"}:
            x = _first_float(data.get("10"))
            y = _first_float(data.get("20"))
            if None in {x, y}:
                continue
            text_value = (data.get("1") or ["text"])[0]
            shapes.append(
                _CadShape(
                    suggestion_type="point",
                    points=[(x, y)],
                    label=text_value.strip()[:255] or "text",
                    rationale=f"Extracted {entity_type} entity from layer '{layer}'.",
                    layer=layer,
                    confidence=0.82,
                )
            )
    return shapes


def _bounds(points: list[tuple[float, float]]) -> tuple[float, float, float, float] | None:
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _normalize_points(
    points: list[tuple[float, float]],
    *,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
) -> list[dict[str, float]]:
    width = max(max_x - min_x, 1e-9)
    height = max(max_y - min_y, 1e-9)
    normalized: list[dict[str, float]] = []
    for x, y in points:
        x_norm = _clamp_norm((x - min_x) / width)
        y_norm = _clamp_norm(1.0 - ((y - min_y) / height))
        normalized.append({"x": round(x_norm, 6), "y": round(y_norm, 6)})
    return normalized


def _prompt_tokens(prompt: str) -> list[str]:
    tokens = [token.lower() for token in re.findall(r"[A-Za-z0-9_]+", prompt or "")]
    return [token for token in tokens if len(token) >= 3 and token not in _STOPWORDS]


def _prompt_score(shape: _CadShape, prompt_tokens: list[str]) -> int:
    if not prompt_tokens:
        return 0
    text = f"{shape.label} {shape.layer}".lower()
    return sum(1 for token in prompt_tokens if token in text)


class DXFAnalysisProvider(BaseAnalysisProvider):
    """Extract geometry suggestions directly from ASCII DXF entities."""

    def run_analysis(self, plan_sheet, user_prompt: str, **kwargs: Any) -> list[dict]:
        plan_path = get_plan_file_path(plan_sheet.storage_key)
        if not plan_path.exists():
            raise RuntimeError("Plan file not found for CAD analysis.")
        if plan_file_type_from_storage_key(plan_sheet.storage_key) != "dxf":
            raise RuntimeError("DXF CAD provider requires a .dxf plan sheet.")
        raw = plan_path.read_bytes()
        if b"\x00" in raw[:2048]:
            raise RuntimeError("Binary DXF files are not supported yet. Upload ASCII DXF.")
        text = raw.decode("utf-8", errors="ignore")
        pairs = _iter_dxf_pairs(text)
        if not pairs:
            raise RuntimeError("DXF file could not be parsed (no code/value pairs found).")
        entities = _extract_entity_blocks(pairs)
        shapes = _extract_shapes(entities)
        if not shapes:
            raise RuntimeError("No supported DXF entities found in ENTITIES section.")

        all_points: list[tuple[float, float]] = []
        for shape in shapes:
            all_points.extend(shape.points)
        bounds = _bounds(all_points)
        if bounds is None:
            raise RuntimeError("DXF parsing produced no valid geometry points.")
        min_x, min_y, max_x, max_y = bounds

        prompt_tokens = _prompt_tokens(user_prompt)
        scored = [(shape, _prompt_score(shape, prompt_tokens)) for shape in shapes]
        scored.sort(key=lambda item: item[1], reverse=True)
        if prompt_tokens and any(score > 0 for _, score in scored):
            scored = [item for item in scored if item[1] > 0]

        max_items = max(1, int(getattr(settings, "PRECONSTRUCTION_CAD_MAX_SUGGESTIONS", 250)))
        out: list[dict[str, Any]] = []
        for shape, _score in scored[:max_items]:
            normalized_points = _normalize_points(
                shape.points,
                min_x=min_x,
                min_y=min_y,
                max_x=max_x,
                max_y=max_y,
            )
            if shape.suggestion_type == "point":
                if not normalized_points:
                    continue
                geometry_json: dict[str, Any] = {
                    "type": "point",
                    "x": normalized_points[0]["x"],
                    "y": normalized_points[0]["y"],
                }
            elif shape.suggestion_type in {"polygon", "polyline"}:
                min_points = 3 if shape.suggestion_type == "polygon" else 2
                if len(normalized_points) < min_points:
                    continue
                geometry_json = {"type": shape.suggestion_type, "points": normalized_points}
            else:
                continue

            out.append(
                {
                    "suggestion_type": shape.suggestion_type,
                    "geometry_json": geometry_json,
                    "label": shape.label[:255],
                    "rationale": shape.rationale,
                    "confidence": round(_clamp_norm(shape.confidence), 4),
                }
            )

        if not out:
            raise RuntimeError("DXF analysis produced no valid suggestions after normalization.")
        return out
