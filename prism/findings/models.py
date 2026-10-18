"""Normalised finding data model.

Every field required by the requirement text is present on :class:`Finding`, and
``to_dict`` is the single canonical serialisation used by both the JSON report and the
API, so the two can never drift apart.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from prism.core.types import CONFIDENCE_MEANING, Confidence, FindingClass, Severity


@dataclass(frozen=True)
class FindingLocation:
    """Where a finding applies.

    ``line`` is ``None`` when the new-side line could not be derived from the diff. A
    missing line is reported as missing; it is never invented.
    """

    path: str
    line: int | None = None
    end_line: int | None = None
    symbol: str | None = None
    hunk_section: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "end_line": self.end_line,
            "symbol": self.symbol,
            "hunk_section": self.hunk_section,
        }

    def describe(self) -> str:
        if self.line is not None and self.symbol:
            return f"{self.path}:{self.line} ({self.symbol})"
        if self.line is not None:
            return f"{self.path}:{self.line}"
        if self.symbol:
            return f"{self.path} ({self.symbol})"
        return self.path


@dataclass(frozen=True)
class Finding:
    """A single, normalised review finding."""

    finding_id: str
    rule_id: str
    category: str
    title: str
    severity: Severity
    confidence: Confidence
    finding_class: FindingClass
    location: FindingLocation
    message: str
    evidence: tuple[str, ...] = ()
    risk: str = ""
    remediation: str = ""
    test_recommendation: str | None = None
    documentation: str | None = None
    signature: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def deterministic(self) -> bool:
        return self.finding_class is FindingClass.DETERMINISTIC

    @property
    def confidence_meaning(self) -> str:
        return CONFIDENCE_MEANING[Confidence(self.confidence)]

    def sort_key(self) -> tuple[int, str, int, str]:
        """Deterministic ordering key: severity desc, path, line, rule."""
        from prism.core.types import severity_rank

        return (
            -severity_rank(self.severity),
            self.location.path,
            self.location.line if self.location.line is not None else -1,
            self.rule_id,
        )

    def to_dict(self, *, include_confidence_meaning: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "finding_id": self.finding_id,
            "rule_id": self.rule_id,
            "category": self.category,
            "title": self.title,
            "severity": Severity(self.severity).value,
            "confidence": Confidence(self.confidence).value,
            "class": FindingClass(self.finding_class).value,
            "deterministic": self.deterministic,
            "location": self.location.to_dict(),
            "message": self.message,
            "evidence": list(self.evidence),
            "risk": self.risk,
            "remediation": self.remediation,
            "test_recommendation": self.test_recommendation,
            "documentation": self.documentation,
            "signature": self.signature,
            "metadata": dict(self.metadata),
        }
        if include_confidence_meaning:
            payload["confidence_meaning"] = self.confidence_meaning
        return payload


@dataclass(frozen=True)
class ToolReport:
    """Outcome of an optional external tool, reported honestly either way."""

    name: str
    status: str
    version: str | None = None
    exit_code: int | None = None
    findings_imported: int = 0
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "version": self.version,
            "exit_code": self.exit_code,
            "findings_imported": self.findings_imported,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ScopeReport:
    """What was analysed, what was skipped, and why."""

    files_in_diff: int = 0
    files_analysed: int = 0
    files_skipped: int = 0
    files_unsupported_language: int = 0
    files_without_full_source: int = 0
    added_lines: int = 0
    removed_lines: int = 0
    skipped: tuple[Mapping[str, Any], ...] = ()
    diagnostics: tuple[str, ...] = ()
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_in_diff": self.files_in_diff,
            "files_analysed": self.files_analysed,
            "files_skipped": self.files_skipped,
            "files_unsupported_language": self.files_unsupported_language,
            "files_without_full_source": self.files_without_full_source,
            "added_lines": self.added_lines,
            "removed_lines": self.removed_lines,
            "skipped": [dict(item) for item in self.skipped],
            "diagnostics": list(self.diagnostics),
            "truncated": self.truncated,
            "complete": not self.truncated,
        }

    @property
    def complete(self) -> bool:
        return not self.truncated


@dataclass(frozen=True)
class ReviewResult:
    """The full outcome of one review."""

    mode: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    findings: tuple[Finding, ...] = ()
    scope: ScopeReport = field(default_factory=ScopeReport)
    tools: tuple[ToolReport, ...] = ()
    coverage: Mapping[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()
    rule_catalog: Mapping[str, Any] = field(default_factory=dict)
    engine_version: str = ""
    generated_at: str | None = None
    suppressed: tuple[Mapping[str, Any], ...] = ()

    @property
    def counts_by_severity(self) -> dict[str, int]:
        counts = {sev.value: 0 for sev in Severity}
        for finding in self.findings:
            counts[Severity(finding.severity).value] += 1
        return counts

    @property
    def counts_by_category(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.category] = counts.get(finding.category, 0) + 1
        return dict(sorted(counts.items()))

    def to_dict(self, *, include_confidence_meaning: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": "1.0",
            "engine": {"name": "PRISM", "version": self.engine_version, "mode": self.mode},
            "metadata": dict(self.metadata),
            "scope": self.scope.to_dict(),
            "summary": {
                "total_findings": len(self.findings),
                "by_severity": self.counts_by_severity,
                "by_category": self.counts_by_category,
                "deterministic": sum(1 for f in self.findings if f.deterministic),
                "heuristic": sum(1 for f in self.findings if not f.deterministic),
            },
            "findings": [
                finding.to_dict(include_confidence_meaning=include_confidence_meaning)
                for finding in self.findings
            ],
            "tools": [tool.to_dict() for tool in self.tools],
            "coverage": dict(self.coverage),
            "suppressed_findings": [dict(item) for item in self.suppressed],
            "limitations": list(self.limitations),
            "rule_catalog": dict(self.rule_catalog),
        }
        if self.generated_at is not None:
            payload["generated_at"] = self.generated_at
        return payload
