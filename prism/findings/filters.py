"""Finding policy: severity threshold, rule exclusion, severity overrides.

Filtering is explicit and recorded. A suppressed finding is not deleted from reality: the
report lists what was suppressed and under which policy, so a clean report can never be
mistaken for "no problems found".
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from prism.core.config import PrismConfig
from prism.core.types import Severity, severity_at_least
from prism.findings.models import Finding


def apply_policy(
    findings: Iterable[Finding],
    config: PrismConfig,
) -> tuple[list[Finding], list[dict[str, Any]]]:
    """Apply severity overrides, rule exclusions and the minimum-severity threshold.

    Returns ``(kept, suppressed)`` where each suppression entry records the finding ID,
    rule ID and the exact rule that removed it.
    """
    kept: list[Finding] = []
    suppressed: list[dict[str, Any]] = []
    excluded = {rule.strip() for rule in config.excluded_rules if rule.strip()}
    minimum = Severity(config.min_severity)
    overrides = {
        str(rule): Severity(severity) for rule, severity in dict(config.severity_overrides).items()
    }

    for finding in findings:
        if finding.rule_id in excluded:
            suppressed.append(
                {
                    "finding_id": finding.finding_id,
                    "rule_id": finding.rule_id,
                    "reason": "rule_excluded_by_configuration",
                    "policy": "excluded_rules",
                }
            )
            continue
        if finding.rule_id in overrides:
            finding = _with_severity(finding, overrides[finding.rule_id])
        if not severity_at_least(finding.severity, minimum):
            suppressed.append(
                {
                    "finding_id": finding.finding_id,
                    "rule_id": finding.rule_id,
                    "reason": "below_minimum_severity",
                    "policy": f"min_severity={minimum.value}",
                }
            )
            continue
        kept.append(finding)

    return kept, suppressed


def _with_severity(finding: Finding, severity: Severity) -> Finding:
    from dataclasses import replace

    metadata = dict(finding.metadata)
    metadata["severity_overridden_from"] = Severity(finding.severity).value
    return replace(finding, severity=severity, metadata=metadata)


def summarize_suppressions(suppressed: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Count suppressions per policy for the report's scope section."""
    counts: dict[str, int] = {}
    for item in suppressed:
        policy = str(item.get("policy", "unknown"))
        counts[policy] = counts.get(policy, 0) + 1
    return dict(sorted(counts.items()))
