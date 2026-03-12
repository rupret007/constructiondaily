"""CAD analysis provider backed by DXF parsing (with optional DWG conversion)."""

from __future__ import annotations

from typing import Any

from preconstruction.cad import build_cad_suggestions

from .base import BaseAnalysisProvider


class DXFAnalysisProvider(BaseAnalysisProvider):
    """Extract geometry suggestions directly from CAD entities."""

    def run_analysis(self, plan_sheet, user_prompt: str, **kwargs: Any) -> list[dict]:
        return build_cad_suggestions(plan_sheet, user_prompt or "")
