"""Provider registry for plan analysis. Enables pluggable backends (mock, future OCR/CV/CAD)."""

from __future__ import annotations

from .base import BaseAnalysisProvider
from .mock import MockAnalysisProvider

_REGISTRY: dict[str, type[BaseAnalysisProvider]] = {
    "mock": MockAnalysisProvider,
}


def get_provider(provider_name: str) -> BaseAnalysisProvider:
    """Return the analysis provider for the given name. Raises ValueError if unknown."""
    if provider_name not in _REGISTRY:
        raise ValueError(f"Unknown provider: {provider_name}. Known: {list(_REGISTRY.keys())}")
    return _REGISTRY[provider_name]()
