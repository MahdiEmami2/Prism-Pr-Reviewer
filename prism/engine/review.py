"""Review engine: diff in, normalised findings out.

The engine is the only place that knows how the pieces fit together, which keeps the
analyzers free of orchestration concerns and keeps the untrusted-input boundary in one
place. Everything it hands to an analyzer is either a parsed diff or in-memory text; no
analyzer ever receives a filesystem path to read or a way to execute anything.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from prism.analyzers.base import AnalysisContext
from prism.analyzers.registry import RuleRegistry, build_default_registry
from prism.analyzers.test_awareness import coverage_findings
from prism.core.config import PrismConfig
from prism.core.exceptions import PrismError
from prism.core.logging_setup import get_logger
from prism.core.types import FileStatus, ReviewMode
from prism.diff.mapping import (
    build_added_line_fragment,
    reconstruct_new_side,
)
from prism.diff.parser import ParsedDiff
from prism.findings.dedupe import deduplicate
from prism.findings.filters import apply_policy
from prism.findings.models import Finding, ReviewResult, ScopeReport, ToolReport

logger = get_logger("engine")

#: Languages PRISM has deterministic rules for.
SUPPORTED_EXTENSIONS = (".py",)

BASE_LIMITATIONS: tuple[str, ...] = (
    "Static analysis only: PRISM never imports, compiles or executes analysed code, so it "
    "cannot prove runtime behaviour.",
    "A finding describes what the diff contains, not what the program does when it runs.",
    "Findings are limited to changed lines. Pre-existing problems on unchanged lines are "
    "out of scope for a pull-request review.",
    "Rules in the 'heuristic' class are review prompts derived from patterns. They have a "
    "measurable false-positive rate and are never presented as proof.",
)


@dataclass
class ReviewInput:
    """Everything needed for one review run."""

    parsed: ParsedDiff
    mode: ReviewMode = ReviewMode.DIFF
    metadata: Mapping[str, Any] = field(default_factory=dict)


class ReviewEngine:
    """Runs the configured analyzers over a parsed diff."""

    def __init__(
        self,
        config: PrismConfig | None = None,
        registry: RuleRegistry | None = None,
    ) -> None:
        self.config = config or PrismConfig()
        self.registry = registry or build_default_registry(
            include_external=self.config.enable_external_tools
        )

    # ------------------------------------------------------------------ inputs

    def analyze(
        self,
        parsed: ParsedDiff,
        *,
        mode: ReviewMode = ReviewMode.DIFF,
        metadata: Mapping[str, Any] | None = None,
        coverage: Mapping[str, Any] | None = None,
        tools: Sequence[ToolReport] = (),
    ) -> ReviewResult:
        """Analyse a parsed diff and return a normalised review result."""
        coverage = dict(coverage or {})
        findings, scope = analyze_parsed_diff(parsed, self.config, self.registry, coverage=coverage)

        suppressed: list[Mapping[str, Any]] = []
        findings, suppressed = apply_policy(findings, self.config)

        coverage_report = coverage.get("summary")
        limitations = list(BASE_LIMITATIONS)
        limitations.extend(_scope_limitations(scope, parsed))
        if coverage.get("available"):
            limitations.append(
                "Coverage data comes from the supplied report; staleness relative to this "
                "diff cannot be verified."
            )
        else:
            limitations.append(
                "No coverage report was supplied, so no statement about test coverage is made."
            )
        if self.config.enable_external_tools:
            limitations.append(
                "Optional external scanners were enabled; their findings are imported with "
                "fixed severities and are not re-validated by PRISM."
            )

        return ReviewResult(
            mode=ReviewMode(mode).value,
            metadata=dict(metadata or {}),
            findings=tuple(findings),
            scope=scope,
            tools=tuple(tools),
            coverage=(
                coverage_report
                if isinstance(coverage_report, Mapping)
                else dict(coverage) or {"available": False, "reason": "no report supplied"}
            ),
            limitations=tuple(limitations),
            rule_catalog=self.registry.catalog(),
            engine_version=_engine_version(),
            suppressed=tuple(suppressed),
        )


def analyze_parsed_diff(
    parsed: ParsedDiff,
    config: PrismConfig,
    registry: RuleRegistry | None = None,
    *,
    coverage: Mapping[str, Any] | None = None,
) -> tuple[list[Finding], ScopeReport]:
    """Run every analyzer over every file and build the scope report."""
    registry = registry or build_default_registry(include_external=config.enable_external_tools)
    coverage = dict(coverage or {})
    findings: list[Finding] = []

    files_analysed = 0
    files_unsupported = 0
    files_without_full_source = 0
    # Skip records arrive in two shapes: SkipRecord dataclasses from the diff parser, and
    # plain mappings from the GitHub source (which carry the API's own status). Both are
    # normalised here so every consumer sees one shape.
    skipped: list[dict[str, Any]] = [_normalize_skip(record) for record in parsed.skipped]
    diagnostics: list[str] = list(parsed.diagnostics)
    changed_paths: list[str] = []
    changed_by_file: dict[str, dict[int, str]] = {}

    for file in parsed.files:
        if file.status is not FileStatus.DELETED:
            changed_paths.append(file.path)
        added = {
            line.new_lineno: line.content
            for line in file.added_lines
            if line.new_lineno is not None
        }
        if added:
            changed_by_file[file.path] = added

        if not file.analyzable:
            continue

        is_python = file.extension in SUPPORTED_EXTENSIONS
        context = AnalysisContext(
            file=file,
            config=config,
            added_lines=added,
            full_source=reconstruct_new_side(file),
            fragment=None,
            fragment_line_map=(),
        )
        if is_python and context.full_source is None:
            fragment = build_added_line_fragment(file)
            if fragment is not None:
                context = AnalysisContext(
                    file=file,
                    config=config,
                    added_lines=added,
                    full_source=None,
                    fragment=fragment[0],
                    fragment_line_map=fragment[1],
                )
            else:
                files_without_full_source += 1
                skipped.append(
                    {
                        "path": file.path,
                        "reason": "no_analyzable_source_view",
                        "detail": ("the patch contains no added Python lines that can be parsed"),
                    }
                )
        if is_python and context.analysis_view == "fragment":
            diagnostics.append(
                f"{file.path}: analysed from the added-lines fragment only; constructs that "
                "depend on unchanged surrounding context may be missed"
            )
        if not is_python:
            files_unsupported += 1
            skipped.append(
                {
                    "path": file.path,
                    "reason": "unsupported_language",
                    "detail": (
                        f"no deterministic rules for '{file.extension or 'no extension'}'; "
                        "credential patterns were still checked"
                    ),
                }
            )

        produced = 0
        for analyzer in registry.analyzers():
            analyzer_name = getattr(analyzer, "name", analyzer.__class__.__name__)
            try:
                for finding in analyzer.analyze(context):
                    findings.append(finding)
                    produced += 1
            except PrismError as exc:
                diagnostics.append(f"{file.path}: analyzer {analyzer_name} failed: {exc.code}")
            except Exception as exc:
                diagnostics.append(
                    f"{file.path}: analyzer {analyzer_name} raised "
                    f"{type(exc).__name__}; the file was partially analysed"
                )
        if is_python and context.analysis_view != "none":
            files_analysed += 1

    # Review-level analyzers (test awareness). Their per-file entry point returns nothing;
    # the aggregate check is driven from the review's changed-path set.
    for analyzer in registry.analyzers():
        analyze_review = getattr(analyzer, "analyze_review", None)
        if analyze_review is None:
            continue
        try:
            review_outcome = analyze_review(changed_paths, config)
        except PrismError as exc:
            diagnostics.append(f"review-level analyzer failed: {exc.code}")
            continue
        except Exception as exc:
            diagnostics.append(f"review-level analyzer failed: {type(exc).__name__}")
            continue
        if review_outcome.finding is not None:
            findings.append(review_outcome.finding)

    # Coverage-driven findings.
    if coverage.get("available"):
        cov_findings, _ = coverage_findings(
            coverage=coverage, changed_paths_by_file=changed_by_file, config=config
        )
        findings.extend(cov_findings)

    merged, merge_log = deduplicate(findings)
    if merge_log:
        logger.debug("deduplicated %d finding group(s)", len(merge_log))

    scope = ScopeReport(
        files_in_diff=len(parsed.files),
        files_analysed=files_analysed,
        files_skipped=len(skipped),
        files_unsupported_language=files_unsupported,
        files_without_full_source=files_without_full_source,
        added_lines=parsed.total_added_lines,
        removed_lines=parsed.total_removed_lines,
        skipped=tuple(skipped),
        diagnostics=tuple(diagnostics),
        truncated=parsed.truncated,
    )
    return merged, scope


def _normalize_skip(record: Any) -> dict[str, Any]:
    """Normalise a skip record into the mapping shape the scope report expects."""
    if isinstance(record, Mapping):
        return {
            "path": record.get("path"),
            "reason": str(record.get("reason") or "skipped"),
            "detail": str(record.get("detail") or ""),
        }
    return {
        "path": getattr(record, "path", None),
        "reason": str(getattr(record, "reason", "skipped")),
        "detail": str(getattr(record, "detail", "") or ""),
    }


def _scope_limitations(scope: ScopeReport, parsed: ParsedDiff) -> list[str]:
    notes: list[str] = []
    if scope.files_unsupported_language:
        notes.append(
            f"{scope.files_unsupported_language} file(s) use a language PRISM has no "
            "deterministic rules for; only credential patterns were applied to them."
        )
    if scope.files_without_full_source:
        notes.append(
            f"{scope.files_without_full_source} Python file(s) could not be analysed because "
            "the patch contains no parseable added-line view."
        )
    if scope.files_skipped:
        notes.append(
            f"{scope.files_skipped} file(s) were skipped; the scope section lists each reason."
        )
    if parsed.truncated:
        notes.append("The diff exceeded a configured limit and was only partially processed.")
    return notes


def _engine_version() -> str:
    from prism import __version__

    return __version__


__all__ = [
    "SUPPORTED_EXTENSIONS",
    "ReviewEngine",
    "ReviewInput",
    "analyze_parsed_diff",
]
