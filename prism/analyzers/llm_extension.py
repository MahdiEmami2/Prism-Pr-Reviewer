"""Optional LLM extension point.

The requirement text allows an optional provider abstraction with strict conditions. The
most honest implementation of those conditions in this project is an interface plus a
deterministic null provider:

* the extension is **disabled by default** and never required for any functionality;
* no provider is implemented, so no API key exists, is read, or is needed;
* a model-derived finding would be labelled ``heuristic`` and would carry the same
  re-validation of path and line against the real diff;
* an LLM can never suppress a deterministic finding: :func:`merge_llm_findings` only ever
  adds findings.

No model evaluation result is claimed anywhere, because none was measured.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from prism.analyzers.base import AnalysisContext
from prism.core.exceptions import ConfigError
from prism.core.types import Confidence, FindingClass, Severity
from prism.findings.identity import compute_finding_id
from prism.findings.models import Finding, FindingLocation


@dataclass(frozen=True)
class LlmSuggestion:
    """A raw, untrusted model suggestion."""

    rule_hint: str
    path: str
    line: int | None
    message: str
    explanation: str = ""
    suggested_fix: str = ""


class LlmProvider(Protocol):
    """Minimal provider interface. Implementations must be explicit opt-in."""

    name: str

    def available(self) -> bool:
        """Whether the provider is configured and usable."""

    def suggest(self, context: AnalysisContext) -> Sequence[LlmSuggestion]:
        """Return raw suggestions; never trusted without validation."""


class NullProvider:
    """Deterministic fallback: always available, never produces suggestions."""

    name = "null"

    def available(self) -> bool:
        return True

    def suggest(self, _context: AnalysisContext) -> Sequence[LlmSuggestion]:
        # A deterministic review needs no provider, so the fallback contributes nothing and
        # can never fabricate a suggestion.
        return ()


ALLOWED_LLM_PATH_PREFIX = ("docs/", "src/", "prism/", "tests/")


def validate_suggestion(
    suggestion: LlmSuggestion,
    *,
    known_paths: Iterable[str],
    added_lines: Mapping[str, Mapping[int, str]],
) -> Finding | None:
    """Convert a suggestion into a finding only if it survives validation.

    Every model-supplied path and line number is checked against the actual diff. A
    suggestion naming a file that is not in the diff, or a line that is not a changed line,
    is discarded - the model's claim is not evidence.
    """
    known = set(known_paths)
    if suggestion.path not in known:
        return None
    if suggestion.line is not None and suggestion.line not in added_lines.get(suggestion.path, {}):
        return None
    if not suggestion.path:
        return None
    signature = f"llm:{suggestion.rule_hint}:{suggestion.message}"
    return Finding(
        finding_id=compute_finding_id(
            rule_id=f"LLM-{suggestion.rule_hint.upper()}",
            path=suggestion.path,
            symbol=None,
            signature=signature,
        ),
        rule_id=f"LLM-{suggestion.rule_hint.upper()}",
        category="ai_suggestion",
        title=suggestion.message[:120],
        severity=Severity.INFORMATIONAL,
        confidence=Confidence.LOW,
        finding_class=FindingClass.HEURISTIC,
        location=FindingLocation(path=suggestion.path, line=suggestion.line),
        message=suggestion.message,
        evidence=(),
        risk=suggestion.explanation,
        remediation=suggestion.suggested_fix,
        documentation="docs/ANALYSIS_RULES.md#optional-llm-extension",
        signature=signature,
        metadata={"source": "llm_extension", "validated_against_diff": True},
    )


def merge_llm_findings(deterministic: Sequence[Finding], extra: Sequence[Finding]) -> list[Finding]:
    """Union of both sets. An LLM can add findings and can never remove one."""
    merged = list(deterministic)
    seen = {finding.finding_id for finding in merged}
    for finding in extra:
        if finding.finding_id not in seen:
            merged.append(finding)
            seen.add(finding.finding_id)
    return merged


def get_provider(name: str, *, enabled: bool) -> LlmProvider:
    """Return the configured provider.

    Raises :class:`ConfigError` for any real provider, because none is implemented. This is
    deliberate: failing loudly is better than pretending an integration exists.
    """
    if not enabled:
        return NullProvider()
    if name in {"", "null", "none"}:
        return NullProvider()
    raise ConfigError(
        "No LLM provider is implemented in this release.",
        details={
            "requested": name,
            "available": ["null"],
            "note": "The extension point exists, but no provider ships with this version.",
        },
    )


def provider_metadata(provider: LlmProvider) -> dict[str, Any]:
    """Describe the provider in a report without implying a capability."""
    return {
        "provider": provider.name,
        "available": provider.available(),
        "note": "Heuristic suggestions only; deterministic findings are never suppressed.",
    }


__all__ = [
    "LlmProvider",
    "LlmSuggestion",
    "NullProvider",
    "get_provider",
    "merge_llm_findings",
    "provider_metadata",
    "validate_suggestion",
]
