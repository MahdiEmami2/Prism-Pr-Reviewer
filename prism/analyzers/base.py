"""Analyzer plugin interface.

An analyzer receives one :class:`AnalysisContext` and yields findings. The context carries
exactly what a rule is allowed to know about the diff:

* ``file`` - the parsed file entry (paths, status, hunks),
* ``full_source`` - the complete new-side text **only** when the patch contains it,
* ``added_lines`` - new-side line number to content, for line-level rules,
* ``symbol_index`` - qualified symbol names by line, when the source is complete.

Rules are never handed a path to read from disk and never a way to execute anything. That
keeps the untrusted-input boundary in one place.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from prism.core.config import PrismConfig
from prism.core.types import Confidence, FindingClass, Severity
from prism.diff.parser import FileDiff
from prism.findings.identity import compute_finding_id
from prism.findings.models import Finding, FindingLocation


@dataclass(frozen=True)
class RuleSpec:
    """Static description of a rule, also used to build the rule catalogue."""

    rule_id: str
    title: str
    category: str
    default_severity: Severity
    default_confidence: Confidence
    finding_class: FindingClass
    description: str
    remediation: str
    test_recommendation: str | None = None
    documentation: str | None = None
    languages: tuple[str, ...] = ("python",)

    def to_catalog_entry(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "category": self.category,
            "default_severity": Severity(self.default_severity).value,
            "default_confidence": Confidence(self.default_confidence).value,
            "class": FindingClass(self.finding_class).value,
            "languages": list(self.languages),
            "description": self.description,
            "remediation": self.remediation,
            "test_recommendation": self.test_recommendation,
            "documentation": self.documentation,
        }


@dataclass(frozen=True)
class AnalysisContext:
    """Everything an analyzer may use for one file."""

    file: FileDiff
    config: PrismConfig
    added_lines: Mapping[int, str] = field(default_factory=dict)
    full_source: str | None = None
    fragment: str | None = None
    fragment_line_map: tuple[int | None, ...] = ()
    symbol_index: Mapping[int, str] = field(default_factory=dict)
    coverage: Mapping[str, Any] = field(default_factory=dict)

    @property
    def path(self) -> str:
        return self.file.path

    @property
    def has_full_source(self) -> bool:
        return self.full_source is not None

    @property
    def analysis_view(self) -> str:
        """'complete' | 'fragment' | 'none' - recorded in the report's scope section."""
        if self.full_source is not None:
            return "complete"
        if self.fragment is not None:
            return "fragment"
        return "none"

    @property
    def added_line_numbers(self) -> frozenset[int]:
        return frozenset(self.added_lines)


@runtime_checkable
class Analyzer(Protocol):
    """Structural type every analyzer satisfies."""

    name: str

    def rule_specs(self) -> Sequence[RuleSpec]:
        """Return the rules this analyzer can emit."""

    def analyze(self, context: AnalysisContext) -> Iterable[Finding]:
        """Yield findings for one file."""


class FindingFactory:
    """Builds normalised findings with deterministic IDs for one file."""

    def __init__(self, context: AnalysisContext) -> None:
        self._context = context

    def create(
        self,
        spec: RuleSpec,
        *,
        line: int | None,
        message: str,
        evidence: Sequence[str] = (),
        symbol: str | None = None,
        signature: str = "",
        discriminator: str | None = None,
        severity: Severity | None = None,
        confidence: Confidence | None = None,
        remediation: str | None = None,
        test_recommendation: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        hunk_section: str | None = None,
    ) -> Finding:
        """Create a finding, deriving its stable ID from rule, path, symbol and signature.

        ``line`` must be ``None`` when the new-side line could not be derived. Rules that
        pass a guessed line number would produce misleading reports, so callers are
        expected to use :meth:`line_if_changed` for anchor decisions.
        """
        effective_signature = signature or message
        finding_id = compute_finding_id(
            rule_id=spec.rule_id,
            path=self._context.path,
            symbol=symbol,
            signature=effective_signature,
            discriminator=discriminator,
        )
        return Finding(
            finding_id=finding_id,
            rule_id=spec.rule_id,
            category=spec.category,
            title=spec.title,
            severity=Severity(severity or spec.default_severity),
            confidence=Confidence(confidence or spec.default_confidence),
            finding_class=FindingClass(spec.finding_class),
            location=FindingLocation(
                path=self._context.path,
                line=line,
                symbol=symbol,
                hunk_section=hunk_section,
            ),
            message=message,
            evidence=tuple(evidence),
            risk=getattr(spec, "description", ""),
            remediation=remediation or spec.remediation,
            test_recommendation=test_recommendation or spec.test_recommendation,
            documentation=spec.documentation,
            signature=effective_signature,
            metadata=dict(metadata or {}),
        )

    def line_if_changed(self, candidate: int | None) -> int | None:
        """Return ``candidate`` only when that new-side line is part of the diff."""
        if candidate is None:
            return None
        return candidate if candidate in self._context.added_lines else None
