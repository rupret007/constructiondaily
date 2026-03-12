"""Provider registry for plan analysis. Enables pluggable backends (mock, OpenAI, CAD)."""

from __future__ import annotations

from .base import BaseAnalysisProvider
from .cad_dxf import DXFAnalysisProvider
from .mock import MockAnalysisProvider
from .openai_vision import OpenAIVisionProvider

_REGISTRY: dict[str, type[BaseAnalysisProvider]] = {
    "mock": MockAnalysisProvider,
    "openai_vision": OpenAIVisionProvider,
    "cad_dxf": DXFAnalysisProvider,
}


def get_provider(provider_name: str) -> BaseAnalysisProvider:
    """Return the analysis provider for the given name. Raises ValueError if unknown."""
    if provider_name not in _REGISTRY:
        raise ValueError(f"Unknown provider: {provider_name}. Known: {list(_REGISTRY.keys())}")
    return _REGISTRY[provider_name]()
