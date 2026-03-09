"""Deterministic mock provider for testing the AI suggestion workflow."""

from __future__ import annotations

import hashlib

from .base import BaseAnalysisProvider


# Keywords in user_prompt -> label and suggestion_type
PROMPT_KEYWORDS = {
    "door": ("Door", "rectangle"),
    "doors": ("Doors", "rectangle"),
    "window": ("Window", "rectangle"),
    "windows": ("Windows", "rectangle"),
    "plumbing": ("Plumbing fixture", "point"),
    "fixture": ("Fixture", "point"),
    "fixtures": ("Fixtures", "point"),
    "concrete": ("Concrete area", "polygon"),
    "slab": ("Concrete slab", "polygon"),
    "electrical": ("Electrical fixture", "point"),
    "opening": ("Opening", "rectangle"),
    "openings": ("Openings", "rectangle"),
    "room": ("Room", "polygon"),
    "rooms": ("Rooms", "polygon"),
}


class MockAnalysisProvider(BaseAnalysisProvider):
    """Returns deterministic placeholder suggestions based on prompt keywords and sheet metadata."""

    def run_analysis(self, plan_sheet, user_prompt: str, **kwargs) -> list[dict]:
        suggestions = []
        prompt_lower = (user_prompt or "").lower()
        sheet_title = (getattr(plan_sheet, "title", None) or "").lower()
        sheet_discipline = (getattr(plan_sheet, "discipline", None) or "").lower()
        combined = f"{prompt_lower} {sheet_title} {sheet_discipline}"

        matched = []
        for keyword, (label, stype) in PROMPT_KEYWORDS.items():
            if keyword in combined:
                matched.append((label, stype))

        if not matched:
            matched = [("Custom area", "rectangle")]

        # Deterministic but varied geometry from sheet + prompt hash
        seed = hashlib.sha256(f"{plan_sheet.id}{user_prompt}".encode()).hexdigest()
        for i, (label, stype) in enumerate(matched[:5]):
            # Normalized coords 0-1
            base = (int(seed[i * 4 : i * 4 + 4], 16) % 70) / 100.0
            x, y = 0.1 + base, 0.1 + (i * 0.15) % 0.6
            w, h = 0.15, 0.12
            if stype == "point":
                geometry = {"type": "point", "x": x, "y": y}
            elif stype == "polygon":
                geometry = {
                    "type": "polygon",
                    "points": [
                        {"x": x, "y": y},
                        {"x": x + w, "y": y},
                        {"x": x + w, "y": y + h},
                        {"x": x, "y": y + h},
                    ],
                }
            else:
                geometry = {"type": "rectangle", "x": x, "y": y, "width": w, "height": h}

            confidence = 0.5 + (int(seed[i * 2 : i * 2 + 2], 16) % 50) / 100.0
            suggestions.append({
                "suggestion_type": stype,
                "geometry_json": geometry,
                "label": label,
                "rationale": f"Mock suggestion for '{label}' based on prompt and sheet context.",
                "confidence": round(confidence, 4),
            })
        return suggestions
