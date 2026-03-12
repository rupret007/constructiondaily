"""OpenAI-based vision provider for plan-sheet analysis."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from urllib import error, request

from django.conf import settings

from preconstruction.storage import get_plan_file_path

from .base import BaseAnalysisProvider


class OpenAIVisionProvider(BaseAnalysisProvider):
    """Run analysis with OpenAI Responses API using the first page of the plan sheet."""

    _SCHEMA: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "suggestions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "suggestion_type": {
                            "type": "string",
                            "enum": ["point", "rectangle", "polygon", "polyline"],
                        },
                        "geometry_json": {"type": "object"},
                        "label": {"type": "string"},
                        "rationale": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": [
                        "suggestion_type",
                        "geometry_json",
                        "label",
                        "rationale",
                        "confidence",
                    ],
                },
            },
        },
        "required": ["suggestions"],
    }

    def run_analysis(self, plan_sheet, user_prompt: str, **kwargs: Any) -> list[dict]:
        api_key = settings.PRECONSTRUCTION_OPENAI_API_KEY
        if not api_key:
            raise RuntimeError("PRECONSTRUCTION_OPENAI_API_KEY is not configured.")

        plan_path = get_plan_file_path(plan_sheet.storage_key)
        if not plan_path.exists():
            raise RuntimeError("Plan file not found for OpenAI analysis.")

        image_data_url = self._render_plan_page_data_url(plan_path)
        payload = self._build_payload(plan_sheet, user_prompt or "", image_data_url)
        response_json = self._post_responses(payload, api_key)
        parsed = self._parse_response_payload(response_json)
        suggestions = self._sanitize_suggestions(parsed.get("suggestions", []))
        if not suggestions:
            raise RuntimeError("OpenAI analysis returned no valid suggestions.")
        return suggestions

    def _render_plan_page_data_url(self, plan_path: Path) -> str:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError(
                "PyMuPDF is required for OpenAI plan analysis. Install dependency 'pymupdf'."
            ) from exc

        with fitz.open(plan_path) as pdf:
            if pdf.page_count < 1:
                raise RuntimeError("Plan PDF has no pages.")
            page = pdf.load_page(0)
            rect = page.rect
            max_side = max(rect.width, rect.height, 1.0)
            zoom = min(3.0, 2000.0 / max_side)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            image_bytes = pix.tobytes("png")
        encoded = base64.b64encode(image_bytes).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    def _build_payload(self, plan_sheet, user_prompt: str, image_data_url: str) -> dict[str, Any]:
        max_suggestions = max(1, int(settings.PRECONSTRUCTION_OPENAI_MAX_SUGGESTIONS))
        system_prompt = (
            "You are a construction estimator assistant. Analyze a plan image and return only JSON "
            "that follows the provided schema. Geometry must use normalized coordinates [0,1]. "
            "For rectangles use {type:'rectangle', x, y, width, height}. "
            "For points use {type:'point', x, y}. "
            "For polygons/polylines use {type:'polygon'|'polyline', points:[{x,y},...]} with at least "
            "3 points for polygon and 2 for polyline. "
            f"Return at most {max_suggestions} suggestions sorted by confidence descending."
        )
        user_text = (
            f"Prompt: {user_prompt}\n"
            f"Sheet title: {plan_sheet.title or ''}\n"
            f"Sheet number: {plan_sheet.sheet_number or ''}\n"
            f"Discipline: {plan_sheet.discipline or ''}\n"
            "Find elements relevant to the prompt and provide geometries where they appear."
        )
        return {
            "model": settings.PRECONSTRUCTION_OPENAI_MODEL,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": user_text},
                        {"type": "input_image", "image_url": image_data_url, "detail": "high"},
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "preconstruction_plan_suggestions",
                    "schema": self._SCHEMA,
                    "strict": True,
                }
            },
        }

    def _post_responses(self, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
        base_url = settings.PRECONSTRUCTION_OPENAI_BASE_URL.rstrip("/")
        url = f"{base_url}/responses"
        timeout = max(5, int(settings.PRECONSTRUCTION_ANALYSIS_TIMEOUT_SECONDS))
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"OpenAI request failed with status {exc.code}: {body[:500]}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"OpenAI request failed: {exc.reason}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OpenAI response was not valid JSON.") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("OpenAI response payload had an unexpected shape.")
        return parsed

    def _parse_response_payload(self, response_json: dict[str, Any]) -> dict[str, Any]:
        output_text = response_json.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            try:
                parsed = json.loads(output_text)
            except json.JSONDecodeError as exc:
                raise RuntimeError("OpenAI output_text was not valid JSON.") from exc
            if isinstance(parsed, dict):
                return parsed

        output = response_json.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    text = part.get("text")
                    if not isinstance(text, str) or not text.strip():
                        continue
                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(parsed, dict):
                        return parsed
        raise RuntimeError("OpenAI response did not contain a parseable JSON suggestion payload.")

    def _sanitize_suggestions(self, suggestions: Any) -> list[dict]:
        if not isinstance(suggestions, list):
            return []
        max_items = max(1, int(settings.PRECONSTRUCTION_OPENAI_MAX_SUGGESTIONS))
        out: list[dict] = []
        for suggestion in suggestions[:max_items]:
            if not isinstance(suggestion, dict):
                continue
            suggestion_type = suggestion.get("suggestion_type")
            geometry_json = suggestion.get("geometry_json")
            if suggestion_type not in {"point", "rectangle", "polygon", "polyline"}:
                continue
            if not isinstance(geometry_json, dict):
                continue
            normalized_geometry = self._normalize_geometry(suggestion_type, geometry_json)
            if normalized_geometry is None:
                continue
            label = suggestion.get("label")
            rationale = suggestion.get("rationale")
            confidence = suggestion.get("confidence")
            try:
                confidence_value = float(confidence)
            except (TypeError, ValueError):
                confidence_value = 0.0
            confidence_value = max(0.0, min(1.0, confidence_value))
            out.append({
                "suggestion_type": suggestion_type,
                "geometry_json": normalized_geometry,
                "label": str(label or "").strip()[:255],
                "rationale": str(rationale or "").strip(),
                "confidence": round(confidence_value, 4),
            })
        return out

    def _normalize_geometry(self, suggestion_type: str, geometry: dict[str, Any]) -> dict[str, Any] | None:
        def _clamp(v: Any) -> float:
            try:
                return max(0.0, min(1.0, float(v)))
            except (TypeError, ValueError):
                return 0.0

        if suggestion_type == "point":
            return {"type": "point", "x": _clamp(geometry.get("x")), "y": _clamp(geometry.get("y"))}

        if suggestion_type == "rectangle":
            x = _clamp(geometry.get("x"))
            y = _clamp(geometry.get("y"))
            width = _clamp(geometry.get("width"))
            height = _clamp(geometry.get("height"))
            if width <= 0 or height <= 0:
                return None
            if x + width > 1:
                width = max(0.0, 1.0 - x)
            if y + height > 1:
                height = max(0.0, 1.0 - y)
            if width <= 0 or height <= 0:
                return None
            return {"type": "rectangle", "x": x, "y": y, "width": width, "height": height}

        points = geometry.get("points")
        if not isinstance(points, list):
            return None
        normalized_points: list[dict[str, float]] = []
        for point in points:
            if not isinstance(point, dict):
                continue
            normalized_points.append({"x": _clamp(point.get("x")), "y": _clamp(point.get("y"))})

        if suggestion_type == "polygon":
            if len(normalized_points) < 3:
                return None
            return {"type": "polygon", "points": normalized_points}

        if suggestion_type == "polyline":
            if len(normalized_points) < 2:
                return None
            return {"type": "polyline", "points": normalized_points}

        return None
