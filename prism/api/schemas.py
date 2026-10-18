"""Pydantic request/response models.

The models are the contract: every field the API accepts is declared and constrained here,
and no field exists that would let a caller execute code, name a filesystem path to read, or
supply an arbitrary URL. ``extra="forbid"`` makes an unexpected key an error rather than a
silently ignored input.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SeverityLiteral = Literal["critical", "high", "medium", "low", "informational"]


class StrictModel(BaseModel):
    """Base model: unknown fields are rejected, strings are stripped."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReviewOptions(StrictModel):
    """Per-request review options. Safe defaults; nothing here enables a new capability."""

    min_severity: SeverityLiteral = "informational"
    excluded_rules: list[str] = Field(default_factory=list, max_length=64)
    include_generated_at: bool = False
    include_confidence_meaning: bool = True

    @field_validator("excluded_rules")
    @classmethod
    def _validate_rule_ids(cls, value: list[str]) -> list[str]:
        for rule_id in value:
            if not rule_id or len(rule_id) > 40:
                raise ValueError("rule identifiers must be 1..40 characters")
            if not all(ch.isalnum() or ch in "-_" for ch in rule_id):
                raise ValueError("rule identifiers may contain letters, digits, '-' and '_'")
        return value


class DiffReviewRequest(StrictModel):
    """Analyse a unified diff supplied inline.

    The diff is analysed as data. It is never written to disk, never imported and never
    executed.
    """

    diff: str = Field(..., min_length=1, description="Unified diff text.")
    title: str | None = Field(default=None, max_length=200)
    options: ReviewOptions = Field(default_factory=ReviewOptions)


class GitHubReviewRequest(StrictModel):
    """Analyse a public (or token-visible) GitHub pull request by coordinates."""

    owner: str = Field(..., min_length=1, max_length=39)
    repo: str = Field(..., min_length=1, max_length=100)
    pull_number: int = Field(..., ge=1, le=9_999_999)
    options: ReviewOptions = Field(default_factory=ReviewOptions)


class HealthResponse(StrictModel):
    """Liveness and readiness in one payload."""

    status: Literal["ok", "degraded"]
    version: str
    rule_count: int
    github_token_configured: bool
    external_tools_enabled: bool


class VersionResponse(StrictModel):
    """Version and capability disclosure, without environment values."""

    name: str
    version: str
    api_version: str
    json_schema_version: str
    supported_review_modes: list[str]
    implemented_rule_ids: list[str]
    optional_features: dict[str, bool]
    limitations: list[str]


class ErrorDetail(StrictModel):
    """Machine-readable error body."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(StrictModel):
    """Consistent error envelope for every failure path."""

    success: Literal[False] = False
    error: ErrorDetail


class ReviewResponse(StrictModel):
    """Successful review response: the same document the JSON report contains."""

    success: Literal[True] = True
    review: dict[str, Any]


__all__ = [
    "DiffReviewRequest",
    "ErrorDetail",
    "ErrorResponse",
    "GitHubReviewRequest",
    "HealthResponse",
    "ReviewOptions",
    "ReviewResponse",
    "VersionResponse",
]
