"""Shared enumerations and value semantics.

Severity and confidence are deliberately independent dimensions:

* :class:`Severity` describes *potential impact* if the code ships as-is.
* :class:`Confidence` describes *how strongly the evidence gathered from the diff*
  supports the finding.

A rule that matches a definite language-level defect has high confidence even when the
impact is low, and a contextual risk (for example "this pickle call may deserialise
untrusted data") has lower confidence because the diff alone cannot prove where the data
came from. Never raise a severity to make a report look impressive.
"""

from __future__ import annotations

from enum import Enum


class Severity(str, Enum):
    """Potential impact of the finding."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


SEVERITY_ORDER: dict[Severity, int] = {
    Severity.CRITICAL: 4,
    Severity.HIGH: 3,
    Severity.MEDIUM: 2,
    Severity.LOW: 1,
    Severity.INFORMATIONAL: 0,
}


def severity_rank(severity: Severity | str) -> int:
    """Return the numeric rank of a severity (higher means more impact)."""
    return SEVERITY_ORDER[Severity(severity)]


def severity_at_least(candidate: Severity | str, minimum: Severity | str) -> bool:
    """True when ``candidate`` is at least as severe as ``minimum``."""
    return severity_rank(candidate) >= severity_rank(minimum)


class Confidence(str, Enum):
    """How strongly the diff evidence supports the finding."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


CONFIDENCE_MEANING: dict[Confidence, str] = {
    Confidence.HIGH: "The diff itself contains the complete evidence: the construct is "
    "present in the changed lines and the rule's conclusion does not depend on unseen code.",
    Confidence.MEDIUM: "The construct is present, but concluding real risk needs context "
    "outside the diff (data origin, surrounding configuration, caller behaviour).",
    Confidence.LOW: "The diff only shows a pattern that often correlates with a problem; "
    "the finding is a review prompt and may be a false positive.",
}


class FindingClass(str, Enum):
    """Whether a finding follows from the diff deterministically or from a heuristic."""

    DETERMINISTIC = "deterministic"
    HEURISTIC = "heuristic"


class FileStatus(str, Enum):
    """How a file changed between the two sides of the diff."""

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    BINARY = "binary"
    UNKNOWN = "unknown"


class ReviewMode(str, Enum):
    """Source of the analysed input."""

    DIFF = "local_diff"
    GITHUB = "github_pr"


class ToolStatus(str, Enum):
    """Outcome of an optional external tool invocation."""

    OK = "ok"
    FINDINGS = "findings_reported"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    TIMEOUT = "timeout"
