"""Typed error hierarchy.

Every error carries a stable machine-readable ``code`` and an HTTP status so the FastAPI
layer can map domain errors onto consistent responses without leaking internals. Messages
must never embed tokens, credentials, headers or local filesystem paths.
"""

from __future__ import annotations

from typing import Any


class PrismError(Exception):
    """Base class for all PRISM domain errors."""

    code = "prism_error"
    http_status = 500

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialisable error body shared by the API and the CLI."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class ConfigError(PrismError):
    """Invalid or contradictory configuration value."""

    code = "config_error"
    http_status = 500


class InputValidationError(PrismError):
    """Caller-supplied input failed validation."""

    code = "validation_error"
    http_status = 400


class UnsupportedInputError(InputValidationError):
    """Input format is understood but not supported (for example combined diffs)."""

    code = "unsupported_input"


class InputTooLargeError(PrismError):
    """Input exceeded a configured size limit."""

    code = "input_too_large"
    http_status = 413


class TooManyFilesError(PrismError):
    """Diff or pull request contains more files than the configured limit."""

    code = "too_many_files"
    http_status = 413


class CoverageError(PrismError):
    """Coverage report could not be read or parsed."""

    code = "coverage_error"
    http_status = 400


class ExternalToolError(PrismError):
    """An optional external scanner failed unexpectedly."""

    code = "external_tool_error"
    http_status = 500


class GitHubError(PrismError):
    """Base class for GitHub REST API problems."""

    code = "github_error"
    http_status = 502


class GitHubAuthError(GitHubError):
    """Token missing, invalid or not permitted for this resource."""

    code = "github_auth_error"


class GitHubNotFoundError(GitHubError):
    """Repository or pull request does not exist / is not visible."""

    code = "github_not_found"
    http_status = 404


class GitHubRateLimitError(GitHubError):
    """API rate limit reached."""

    code = "github_rate_limited"
    http_status = 503

    def __init__(
        self,
        message: str,
        *,
        reset_at: str | None = None,
        retry_after: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = dict(details or {})
        if reset_at:
            merged["rate_limit_reset"] = reset_at
        if retry_after:
            merged["retry_after_seconds"] = retry_after
        super().__init__(message, details=merged)
        self.reset_at = reset_at
        self.retry_after = retry_after


class GitHubResponseTooLargeError(GitHubError):
    """A GitHub response exceeded the configured response-size cap."""

    code = "github_response_too_large"


class PaginationLimitError(GitHubError):
    """Pagination stopped at the configured page cap before the listing ended."""

    code = "github_pagination_limit"
