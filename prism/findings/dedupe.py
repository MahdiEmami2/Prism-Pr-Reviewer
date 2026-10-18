"""Deduplication.

Rules may overlap: a single line can be reported by a line-based pattern rule and by an
AST rule, or the same file can be seen twice when a diff is supplied alongside a resolved
source. Duplicate means *same finding ID*, not *same file* - two distinct problems in one
file must both survive.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from prism.findings.models import Finding


def deduplicate(findings: Iterable[Finding]) -> tuple[list[Finding], list[dict[str, str]]]:
    """Collapse findings with identical IDs.

    Returns the surviving findings (deterministically sorted) and a merge log describing
    what was collapsed, so the reduction is auditable rather than silent. When two
    findings share an ID, the one with the smaller evidence tuple is kept; ties are broken
    by rule ID so the choice is stable.
    """
    groups: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        groups[finding.finding_id].append(finding)

    merged: list[Finding] = []
    log: list[dict[str, str]] = []
    for finding_id, items in groups.items():
        if len(items) == 1:
            merged.append(items[0])
            continue
        ordered = sorted(items, key=lambda item: (len(item.evidence), item.rule_id))
        keeper = ordered[0]
        merged.append(keeper)
        log.append(
            {
                "finding_id": finding_id,
                "kept_rule": keeper.rule_id,
                "collapsed": ", ".join(sorted({item.rule_id for item in ordered})),
                "count": str(len(ordered)),
                "reason": "identical finding identity",
            }
        )

    merged.sort(key=lambda item: item.sort_key())
    log.sort(key=lambda item: item["finding_id"])
    return merged, log
