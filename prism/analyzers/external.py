"""Optional adapters for external scanners (Ruff, Bandit).

Design rules taken from the requirement text and the sandbox safety policy:

* Disabled by default. Nothing here runs unless ``enable_external_tools`` is set.
* Tool availability is checked first; absence is a reported status, never an error.
* The subprocess return code is always inspected. Ruff exits 1 when it finds findings and
  >=2 on error; Bandit exits 1 when it finds findings. A non-zero, non-"findings" code is
  reported as a failure with the exit code, and never silently ignored.
* The command is built from a fixed argument list. No shell, no analysed code is executed:
  both tools only read the file.
* Tool output is parsed defensively; a parse failure is reported as a tool failure.
"""

from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404 - fixed argv lists, shell disabled, no diff content passed
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from prism.analyzers.base import AnalysisContext, RuleSpec
from prism.core.types import Confidence, FindingClass, Severity, ToolStatus
from prism.findings.identity import compute_finding_id
from prism.findings.models import Finding, FindingLocation, ToolReport

_DOC = "docs/ANALYSIS_RULES.md"

RUFF_SPEC = RuleSpec(
    rule_id="EXT-RUFF",
    title="External lint finding (Ruff)",
    category="maintainability",
    default_severity=Severity.LOW,
    default_confidence=Confidence.MEDIUM,
    finding_class=FindingClass.DETERMINISTIC,
    description=(
        "Reported by the optional Ruff integration. Severity is a fixed low default: PRISM "
        "does not map Ruff rule codes onto impact levels, because that mapping would be a "
        "guess."
    ),
    remediation="Address the reported lint rule or configure the rule set for this project.",
    documentation=_DOC,
    languages=("python",),
)

BANDIT_SPEC = RuleSpec(
    rule_id="EXT-BANDIT",
    title="External security finding (Bandit)",
    category="security",
    default_severity=Severity.MEDIUM,
    default_confidence=Confidence.MEDIUM,
    finding_class=FindingClass.DETERMINISTIC,
    description=(
        "Reported by the optional Bandit integration. Bandit severity strings map onto "
        "PRISM severities mechanically; PRISM does not elevate them further."
    ),
    remediation="Review the Bandit rule documentation and address or explicitly suppress it.",
    documentation=_DOC,
    languages=("python",),
)

_BANDIT_SEVERITY = {
    "LOW": Severity.LOW,
    "MEDIUM": Severity.MEDIUM,
    "HIGH": Severity.HIGH,
    "UNDEFINED": Severity.LOW,
}


@dataclass(frozen=True)
class ExternalToolResult:
    """Everything an external run produced, including its failures."""

    report: ToolReport
    findings: tuple[Finding, ...] = ()
    raw: MappingLike = None  # type: ignore[assignment]


MappingLike = Any


def _run(args: Sequence[str], *, timeout: float) -> tuple[int, str, str, str | None]:
    """Run a fixed command list with no shell. Returns (rc, stdout, stderr, error)."""
    try:
        completed = subprocess.run(  # noqa: S603  # nosec B603 - fixed argv, no shell
            list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
    except FileNotFoundError:
        return -1, "", "", "executable not found"
    except subprocess.TimeoutExpired:
        return -1, "", "", f"timeout after {timeout}s"
    return completed.returncode, completed.stdout or "", completed.stderr or "", None


def run_ruff(path: str, *, timeout: float = 60.0) -> ExternalToolResult:
    """Run ``ruff check --output-format json`` against one file."""
    if shutil.which("ruff") is None:
        return ExternalToolResult(
            report=ToolReport(
                name="ruff",
                status=ToolStatus.UNAVAILABLE.value,
                detail="ruff executable not found on PATH",
            )
        )
    version_rc, version_out, _, _ = _run(["ruff", "--version"], timeout=timeout)
    version = version_out.strip() if version_rc == 0 else None
    rc, stdout, stderr, error = _run(
        ["ruff", "check", "--output-format", "json", "--no-cache", path], timeout=timeout
    )
    if error is not None:
        status = ToolStatus.TIMEOUT.value if "timeout" in error else ToolStatus.UNAVAILABLE.value
        return ExternalToolResult(
            report=ToolReport(
                name="ruff", status=status, version=version, exit_code=rc, detail=error
            )
        )
    if rc not in (0, 1):
        return ExternalToolResult(
            report=ToolReport(
                name="ruff",
                status=ToolStatus.FAILED.value,
                version=version,
                exit_code=rc,
                detail=(stderr.strip() or "ruff returned an unexpected exit code")[:400],
            )
        )
    try:
        payload = json.loads(stdout or "[]")
    except json.JSONDecodeError:
        return ExternalToolResult(
            report=ToolReport(
                name="ruff",
                status=ToolStatus.FAILED.value,
                version=version,
                exit_code=rc,
                detail="could not parse ruff JSON output",
            )
        )
    findings = tuple(_ruff_finding(item, path) for item in payload if isinstance(item, dict))
    return ExternalToolResult(
        report=ToolReport(
            name="ruff",
            status=(ToolStatus.FINDINGS.value if findings else ToolStatus.OK.value),
            version=version,
            exit_code=rc,
            findings_imported=len(findings),
        ),
        findings=findings,
    )


def _ruff_finding(item: dict[str, Any], path: str) -> Finding:
    code = str(item.get("code") or "unknown")
    row = item.get("location", {}).get("row") if isinstance(item.get("location"), dict) else None
    message = str(item.get("message") or "Ruff finding")
    signature = f"{code}:{message}"
    return Finding(
        finding_id=compute_finding_id(
            rule_id="EXT-RUFF", path=path, symbol=code, signature=signature
        ),
        rule_id="EXT-RUFF",
        category=RUFF_SPEC.category,
        title=f"Ruff {code}: {message[:80]}",
        severity=RUFF_SPEC.default_severity,
        confidence=RUFF_SPEC.default_confidence,
        finding_class=RUFF_SPEC.finding_class,
        location=FindingLocation(path=path, line=int(row) if isinstance(row, int) else None),
        message=message,
        remediation=RUFF_SPEC.remediation,
        documentation=RUFF_SPEC.documentation,
        signature=signature,
        metadata={"tool": "ruff", "code": code, "tool_line": row},
    )


def run_bandit(path: str, *, timeout: float = 60.0) -> ExternalToolResult:
    """Run ``bandit -f json`` against one file."""
    if shutil.which("bandit") is None:
        return ExternalToolResult(
            report=ToolReport(
                name="bandit",
                status=ToolStatus.UNAVAILABLE.value,
                detail="bandit executable not found on PATH",
            )
        )
    version_rc, version_out, _, _ = _run(["bandit", "--version"], timeout=timeout)
    version = version_out.strip().splitlines()[0] if version_rc == 0 and version_out else None
    rc, stdout, stderr, error = _run(["bandit", "-f", "json", "-q", path], timeout=timeout)
    if error is not None:
        status = ToolStatus.TIMEOUT.value if "timeout" in error else ToolStatus.UNAVAILABLE.value
        return ExternalToolResult(
            report=ToolReport(
                name="bandit", status=status, version=version, exit_code=rc, detail=error
            )
        )
    if rc not in (0, 1):
        return ExternalToolResult(
            report=ToolReport(
                name="bandit",
                status=ToolStatus.FAILED.value,
                version=version,
                exit_code=rc,
                detail=(stderr.strip() or "bandit returned an unexpected exit code")[:400],
            )
        )
    try:
        payload = json.loads(stdout or "{}")
        results = payload.get("results", []) if isinstance(payload, dict) else []
    except json.JSONDecodeError:
        return ExternalToolResult(
            report=ToolReport(
                name="bandit",
                status=ToolStatus.FAILED.value,
                version=version,
                exit_code=rc,
                detail="could not parse bandit JSON output",
            )
        )
    findings = tuple(_bandit_finding(item, path) for item in results if isinstance(item, dict))
    return ExternalToolResult(
        report=ToolReport(
            name="bandit",
            status=(ToolStatus.FINDINGS.value if findings else ToolStatus.OK.value),
            version=version,
            exit_code=rc,
            findings_imported=len(findings),
        ),
        findings=findings,
    )


def _bandit_finding(item: dict[str, Any], path: str) -> Finding:
    test_id = str(item.get("test_id") or "unknown")
    text = str(item.get("issue_text") or "Bandit finding")
    severity = _BANDIT_SEVERITY.get(str(item.get("issue_severity", "")).upper(), Severity.LOW)
    line = item.get("line_number")
    signature = f"{test_id}:{text}"
    return Finding(
        finding_id=compute_finding_id(
            rule_id="EXT-BANDIT", path=path, symbol=test_id, signature=signature
        ),
        rule_id="EXT-BANDIT",
        category=BANDIT_SPEC.category,
        title=f"Bandit {test_id}: {text[:80]}",
        severity=severity,
        confidence=BANDIT_SPEC.default_confidence,
        finding_class=BANDIT_SPEC.finding_class,
        location=FindingLocation(path=path, line=int(line) if isinstance(line, int) else None),
        message=text,
        remediation=BANDIT_SPEC.remediation,
        documentation=BANDIT_SPEC.documentation,
        signature=signature,
        metadata={
            "tool": "bandit",
            "test_id": test_id,
            "tool_confidence": item.get("issue_confidence"),
            "tool_line": line,
        },
    )


class ExternalToolAnalyzer:
    """Runs one external tool for a file whose source is available on disk.

    External tools operate on files, not on in-memory diffs, so this analyzer is only used
    by the review-diff mode when the caller supplies the repository root. It never writes
    to the analysed file and never executes repository code.
    """

    name = "external_tools"

    def __init__(self, repo_root: str) -> None:
        self.repo_root = repo_root

    def rule_specs(self) -> Sequence[RuleSpec]:
        return (RUFF_SPEC, BANDIT_SPEC)

    def analyze(self, _context: AnalysisContext) -> Iterable[Finding]:
        # External tools operate on files on disk, not on an in-memory diff, so the analyzer
        # contributes nothing per file. Its findings are produced by the runner helpers above
        # and attached to the review as ToolReports.
        return ()


def build_external_analyzers(repo_root: str = ".") -> list[ExternalToolAnalyzer]:
    """Factory used by the registry when external tools are explicitly enabled."""
    return [ExternalToolAnalyzer(repo_root)]


__all__ = [
    "BANDIT_SPEC",
    "RUFF_SPEC",
    "ExternalToolAnalyzer",
    "ExternalToolResult",
    "build_external_analyzers",
    "run_bandit",
    "run_ruff",
]
