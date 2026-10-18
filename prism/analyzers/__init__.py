"""Public analyzer surface."""

from prism.analyzers.base import (
    AnalysisContext,
    Analyzer,
    FindingFactory,
    RuleSpec,
)
from prism.analyzers.registry import RuleRegistry, build_default_registry

__all__ = [
    "AnalysisContext",
    "Analyzer",
    "FindingFactory",
    "RuleRegistry",
    "RuleSpec",
    "build_default_registry",
]
