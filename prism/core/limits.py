"""Resource-limit policy and enforcement helpers.

All limits are conservative defaults (documented as assumptions M-3 and M-10 in
``docs/SPEC.md``) and are overridable through configuration. Exceeding a limit raises a
typed error carrying both the limit and the observed value, never a silent truncation.
"""

from __future__ import annotations

from dataclasses import dataclass

from prism.core.exceptions import InputTooLargeError, TooManyFilesError

MIB = 1024 * 1024


@dataclass(frozen=True)
class LimitPolicy:
    """Caps applied to one review."""

    max_diff_bytes: int = 5 * MIB
    max_patch_bytes: int = 2 * MIB
    max_files: int = 300
    max_response_bytes: int = 8 * MIB
    max_pages: int = 100
    max_hunk_lines: int = 20_000
    http_timeout_seconds: float = 20.0

    def describe(self) -> dict[str, int | float]:
        """Human-readable limit table, used in the report's limitations section."""
        return {
            "max_diff_bytes": self.max_diff_bytes,
            "max_patch_bytes": self.max_patch_bytes,
            "max_files": self.max_files,
            "max_response_bytes": self.max_response_bytes,
            "max_pages": self.max_pages,
            "max_hunk_lines": self.max_hunk_lines,
            "http_timeout_seconds": self.http_timeout_seconds,
        }


@dataclass(frozen=True)
class LimitApplication:
    """Record of one limit that was evaluated during a review."""

    name: str
    limit: int | float
    observed: int | float
    exceeded: bool

    def describe(self) -> str:
        return (
            f"{self.name}: observed {self.observed} of limit {self.limit}"
            f"{' (exceeded)' if self.exceeded else ''}"
        )


def check_diff_size(observed_bytes: int, policy: LimitPolicy) -> LimitApplication:
    """Raise :class:`InputTooLargeError` when the diff exceeds the byte cap."""
    exceeded = observed_bytes > policy.max_diff_bytes
    if exceeded:
        raise InputTooLargeError(
            "Diff exceeds the configured size limit.",
            details={"limit": policy.max_diff_bytes, "observed": observed_bytes, "unit": "bytes"},
        )
    return LimitApplication("max_diff_bytes", policy.max_diff_bytes, observed_bytes, False)


def check_file_count(observed_files: int, policy: LimitPolicy) -> LimitApplication:
    """Raise :class:`TooManyFilesError` when the diff touches too many files."""
    exceeded = observed_files > policy.max_files
    if exceeded:
        raise TooManyFilesError(
            "Diff contains more files than the configured limit.",
            details={"limit": policy.max_files, "observed": observed_files},
        )
    return LimitApplication("max_files", policy.max_files, observed_files, False)


def patch_within_limit(size_bytes: int, policy: LimitPolicy) -> bool:
    """True when a single file patch may be analysed."""
    return size_bytes <= policy.max_patch_bytes
