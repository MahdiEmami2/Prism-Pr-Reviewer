"""Test-awareness rules.

Two honest capabilities, kept deliberately weak where the evidence is weak:

* ``TST001`` - a review-level heuristic that flags changed source files when the review
  contains no test change at all. It is a *review prompt* with low confidence: a diff can
  legitimately contain no test change (documentation, CI, configuration), and the diff
  cannot show whether tests already exist elsewhere.
* ``TST002`` - coverage information, only ever reported when an actual coverage report is
  supplied *and* that report lists the changed line explicitly. PRISM never derives a
  percentage from the number of test files.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any

from prism.analyzers.base import AnalysisContext, FindingFactory, RuleSpec
from prism.core.config import PrismConfig
from prism.core.types import Confidence, FindingClass, Severity
from prism.findings.models import Finding, FindingLocation

CATEGORY_TESTING = "testing"
_DOC = "docs/ANALYSIS_RULES.md"

#: How many changed source paths are listed in one aggregate TST001 finding.
MAX_LISTED_PATHS = 20

SPECS: dict[str, RuleSpec] = {
    "TST001": RuleSpec(
        rule_id="TST001",
        title="Source changed without any test change in this review",
        category=CATEGORY_TESTING,
        default_severity=Severity.LOW,
        default_confidence=Confidence.LOW,
        finding_class=FindingClass.HEURISTIC,
        description=(
            "The review changes source files but contains no change to a file matching the "
            "configured test conventions. This is a heuristic, not proof that tests are "
            "missing: tests may already cover the behaviour, the convention may not match "
            "this repository, or the change may not need tests at all."
        ),
        remediation=(
            "Confirm that existing tests cover the changed behaviour, or add the missing "
            "test in this pull request."
        ),
        test_recommendation="Add or extend a test that exercises the changed branch.",
        documentation=_DOC,
    ),
    "TST002": RuleSpec(
        rule_id="TST002",
        title="Changed line is not covered by the supplied coverage report",
        category=CATEGORY_TESTING,
        default_severity=Severity.LOW,
        default_confidence=Confidence.MEDIUM,
        finding_class=FindingClass.DETERMINISTIC,
        description=(
            "A supplied Cobertura report lists this changed line and records zero hits. The "
            "report explicitly covers the line, which is stronger than an inference from "
            "the presence or absence of test files."
        ),
        remediation="Add a test that executes this line, or confirm the line is unreachable.",
        documentation=_DOC,
    ),
    "TST003": RuleSpec(
        rule_id="TST003",
        title="Coverage report does not mention a changed file",
        category=CATEGORY_TESTING,
        default_severity=Severity.INFORMATIONAL,
        default_confidence=Confidence.MEDIUM,
        finding_class=FindingClass.HEURISTIC,
        description=(
            "The supplied coverage report contains no entry for a file that this review "
            "changes. The usual cause is an outdated report or a file that is not imported "
            "by the test suite. No percentage is claimed for this file."
        ),
        remediation="Regenerate the coverage report for this revision before drawing conclusions.",
        documentation=_DOC,
    ),
}


@dataclass(frozen=True)
class TestAwarenessResult:
    """Outcome of the review-level test check."""

    test_files_changed: tuple[str, ...]
    source_files_changed: tuple[str, ...]
    test_conventions: tuple[str, ...]
    finding: Finding | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_files_changed": list(self.test_files_changed),
            "source_files_changed_count": len(self.source_files_changed),
            "source_files_changed": list(self.source_files_changed[:MAX_LISTED_PATHS]),
            "source_files_listed_truncated": len(self.source_files_changed) > MAX_LISTED_PATHS,
            "test_conventions": list(self.test_conventions),
            "heuristic_finding_emitted": self.finding is not None,
        }


def is_test_path(path: str, globs: Sequence[str]) -> bool:
    """True when a repository path matches one of the configured test conventions."""
    normalized = path.replace("\\", "/").lstrip("./")
    name = normalized.rsplit("/", 1)[-1]
    return any(fnmatch(normalized, pattern) or fnmatch(name, pattern) for pattern in globs)


def analyze_test_awareness(
    *,
    changed_paths: Sequence[str],
    config: PrismConfig,
    review_path: str = "<review>",
) -> TestAwarenessResult:
    """Compare changed source paths with changed test paths and emit at most one finding."""
    globs = tuple(config.test_file_globs)
    tests = tuple(sorted({p for p in changed_paths if is_test_path(p, globs)}))
    sources = tuple(sorted({p for p in changed_paths if not is_test_path(p, globs)}))

    finding: Finding | None = None
    if sources and not tests:
        listed = sources[:MAX_LISTED_PATHS]
        context = AnalysisContext(
            file=_pseudo_file(review_path),
            config=config,
        )
        factory = FindingFactory(context)
        from prism.findings.identity import compute_finding_id

        signature = "no-test-change:" + ",".join(sorted(listed))
        finding = Finding(
            finding_id=compute_finding_id(
                rule_id="TST001",
                path=review_path,
                symbol=None,
                signature=signature,
            ),
            rule_id="TST001",
            category=CATEGORY_TESTING,
            title=SPECS["TST001"].title,
            severity=SPECS["TST001"].default_severity,
            confidence=SPECS["TST001"].default_confidence,
            finding_class=FindingClass.HEURISTIC,
            location=FindingLocation(path=review_path, line=None),
            message=(
                f"No test file changed in this review, but {len(sources)} source file(s) did."
            ),
            evidence=tuple(listed),
            risk=SPECS["TST001"].description,
            remediation=SPECS["TST001"].remediation,
            test_recommendation=SPECS["TST001"].test_recommendation,
            documentation=SPECS["TST001"].documentation,
            signature=signature,
            metadata={
                "source_files_changed": len(sources),
                "listed_paths": len(listed),
                "listed_truncated": len(sources) > MAX_LISTED_PATHS,
                "test_conventions": list(globs),
            },
        )
        del factory

    return TestAwarenessResult(
        test_files_changed=tests,
        source_files_changed=sources,
        test_conventions=globs,
        finding=finding,
    )


def coverage_findings(
    *,
    coverage: Mapping[str, Any],
    changed_paths_by_file: Mapping[str, Mapping[int, str]],
    review_path: str = "<review>",
    config: PrismConfig | None = None,
) -> tuple[list[Finding], dict[str, Any]]:
    """Emit TST002/TST003 findings from a parsed coverage report.

    Only lines the report explicitly lists are considered. A file the report does not
    mention produces TST003 (informational) and never a percentage.
    """

    findings: list[Finding] = []
    # ``review_path`` and ``config`` are part of the uniform review-level analyzer contract:
    # the engine passes the review context to every such check. This check derives everything
    # it needs from the coverage data and the changed lines, so both are accepted and not used.
    _ = (review_path, config)
    if not coverage.get("available"):
        return findings, coverage

    files = dict(coverage.get("files", {}))
    for path, added in sorted(changed_paths_by_file.items()):
        entry = files.get(path)
        if entry is None:
            findings.append(
                _make(
                    "TST003",
                    path=path,
                    line=None,
                    message=(
                        "Coverage report has no entry for this changed file; no coverage "
                        "conclusion is possible for it."
                    ),
                    signature=f"coverage-missing-file:{path}",
                    evidence=(),
                )
            )
            continue
        uncovered = sorted(line for line in added if line in set(entry.get("uncovered_lines", ())))
        for line in uncovered[:20]:
            findings.append(
                _make(
                    "TST002",
                    path=path,
                    line=line,
                    message="Coverage report lists this changed line with zero hits.",
                    signature=f"uncovered-line:{line}",
                    evidence=(added.get(line, ""),),
                )
            )
    return findings, coverage


def _make(
    rule_id: str,
    *,
    path: str,
    line: int | None,
    message: str,
    signature: str,
    evidence: Sequence[str],
) -> Finding:
    from prism.findings.identity import compute_finding_id

    spec = SPECS[rule_id]
    return Finding(
        finding_id=compute_finding_id(rule_id=rule_id, path=path, symbol=None, signature=signature),
        rule_id=rule_id,
        category=CATEGORY_TESTING,
        title=spec.title,
        severity=spec.default_severity,
        confidence=spec.default_confidence,
        finding_class=FindingClass(spec.finding_class),
        location=FindingLocation(path=path, line=line),
        message=message,
        evidence=tuple(evidence),
        risk=spec.description,
        remediation=spec.remediation,
        test_recommendation=spec.test_recommendation,
        documentation=spec.documentation,
        signature=signature,
    )


def _pseudo_file(path: str):
    from prism.core.types import FileStatus
    from prism.diff.parser import FileDiff

    return FileDiff(old_path=None, new_path=path, status=FileStatus.MODIFIED)


class TestAwarenessAnalyzer:
    """Registry-facing wrapper for the review-level test-awareness check."""

    name = "test_awareness"

    def rule_specs(self) -> Sequence[RuleSpec]:
        return tuple(SPECS.values())

    def analyze(self, _context: AnalysisContext) -> Iterable[Finding]:
        # Test awareness is a review-level property, not a per-file one: the engine calls
        # ``analyze_review`` instead. Returning nothing here keeps the registry uniform.
        return ()

    def analyze_review(
        self, changed_paths: Sequence[str], config: PrismConfig
    ) -> TestAwarenessResult:
        return analyze_test_awareness(changed_paths=changed_paths, config=config)


__all__ = [
    "SPECS",
    "TestAwarenessAnalyzer",
    "TestAwarenessResult",
    "analyze_test_awareness",
    "coverage_findings",
    "is_test_path",
]
