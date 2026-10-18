"""Finding model, normalisation, identity, deduplication and filtering."""

from prism.findings.dedupe import deduplicate
from prism.findings.filters import apply_policy
from prism.findings.identity import (
    compute_finding_id,
    normalize_path,
    normalize_signature,
)
from prism.findings.models import (
    Finding,
    FindingLocation,
    ReviewResult,
    ScopeReport,
    ToolReport,
)

__all__ = [
    "Finding",
    "FindingLocation",
    "ReviewResult",
    "ScopeReport",
    "ToolReport",
    "apply_policy",
    "compute_finding_id",
    "deduplicate",
    "normalize_path",
    "normalize_signature",
]
