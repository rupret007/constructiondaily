"""Abstract interface for plan analysis providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAnalysisProvider(ABC):
    @abstractmethod
    def run_analysis(
        self,
        plan_sheet,
        user_prompt: str,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """
        Run analysis on a plan sheet; return list of suggestion dicts with keys:
        suggestion_type, geometry_json, label, rationale, confidence.
        """
        pass
