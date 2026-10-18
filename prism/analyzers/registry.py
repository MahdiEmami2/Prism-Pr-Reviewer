"""Rule registry.

Analyzers register themselves here; the engine iterates the registry instead of importing
concrete analyzers. Adding a rule means adding a class and one registry entry - no engine
change - which is the extensibility requirement from the analysis-engine section.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from prism.analyzers.base import Analyzer, RuleSpec
from prism.core.exceptions import ConfigError


class RuleRegistry:
    """Ordered collection of analyzers keyed by name."""

    def __init__(self) -> None:
        self._analyzers: dict[str, Analyzer] = {}

    def register(self, analyzer: Analyzer, *, replace: bool = False) -> None:
        name = getattr(analyzer, "name", None)
        if not name:
            raise ConfigError("Analyzer is missing a name.")
        if name in self._analyzers and not replace:
            raise ConfigError("Analyzer already registered.", details={"name": name})
        specs = list(analyzer.rule_specs())
        self._check_unique_rule_ids(specs, name)
        self._analyzers[name] = analyzer

    def _check_unique_rule_ids(self, specs: Sequence[RuleSpec], analyzer_name: str) -> None:
        existing = {spec.rule_id for spec in self.rule_specs()}
        duplicates = sorted({spec.rule_id for spec in specs} & existing)
        if duplicates:
            raise ConfigError(
                "Duplicate rule IDs across analyzers.",
                details={"rule_ids": duplicates, "analyzer": analyzer_name},
            )

    def analyzers(self) -> tuple[Analyzer, ...]:
        return tuple(self._analyzers.values())

    def names(self) -> tuple[str, ...]:
        return tuple(self._analyzers)

    def rule_specs(self) -> tuple[RuleSpec, ...]:
        collected: list[RuleSpec] = []
        for analyzer in self._analyzers.values():
            collected.extend(analyzer.rule_specs())
        return tuple(sorted(collected, key=lambda spec: spec.rule_id))

    def rule_ids(self) -> tuple[str, ...]:
        return tuple(spec.rule_id for spec in self.rule_specs())

    def catalog(self) -> dict[str, dict[str, object]]:
        """Machine-readable rule catalogue embedded in every report."""
        return {spec.rule_id: spec.to_catalog_entry() for spec in self.rule_specs()}

    def find(self, rule_id: str) -> RuleSpec | None:
        for spec in self.rule_specs():
            if spec.rule_id == rule_id:
                return spec
        return None

    def extend(self, analyzers: Iterable[Analyzer]) -> None:
        for analyzer in analyzers:
            self.register(analyzer)


def build_default_registry(*, include_external: bool = False) -> RuleRegistry:
    """Create the registry used by the CLI and the API.

    External tool analyzers are only registered when explicitly enabled, so the default
    path has no subprocess dependency at all.
    """
    from prism.analyzers.python_rules import PythonAstAnalyzer
    from prism.analyzers.secrets import SecretPatternAnalyzer
    from prism.analyzers.test_awareness import TestAwarenessAnalyzer

    registry = RuleRegistry()
    registry.register(PythonAstAnalyzer())
    registry.register(SecretPatternAnalyzer())
    registry.register(TestAwarenessAnalyzer())
    if include_external:
        from prism.analyzers.external import build_external_analyzers

        registry.extend(build_external_analyzers())
    return registry
