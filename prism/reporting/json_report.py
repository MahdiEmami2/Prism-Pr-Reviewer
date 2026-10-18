"""JSON report rendering.

Deterministic by construction: keys are written in a fixed order (the dataclass field
order), findings are pre-sorted by the engine, and ``generated_at`` is only included when
explicitly enabled. Two runs over identical input therefore produce byte-identical output,
which the test suite asserts.
"""

from __future__ import annotations

import json
from typing import Any

from prism.findings.models import ReviewResult


def render_json(
    result: ReviewResult,
    *,
    indent: int = 2,
    include_confidence_meaning: bool = True,
) -> str:
    """Serialise a review result to a stable JSON document."""
    payload = result.to_dict(include_confidence_meaning=include_confidence_meaning)
    return json.dumps(payload, indent=indent, ensure_ascii=False, sort_keys=False) + "\n"


def schema_summary() -> dict[str, Any]:
    """Describe the top-level JSON shape so the docs can stay in step with the code."""
    return {
        "schema_version": "1.0",
        "top_level_keys": [
            "schema_version",
            "engine",
            "metadata",
            "scope",
            "summary",
            "findings",
            "tools",
            "coverage",
            "suppressed_findings",
            "limitations",
            "rule_catalog",
        ],
        "optional_keys": ["generated_at"],
        "finding_keys": [
            "finding_id",
            "rule_id",
            "category",
            "title",
            "severity",
            "confidence",
            "class",
            "deterministic",
            "location",
            "message",
            "evidence",
            "risk",
            "remediation",
            "test_recommendation",
            "documentation",
            "signature",
            "metadata",
            "confidence_meaning",
        ],
    }


__all__ = ["render_json", "schema_summary"]
