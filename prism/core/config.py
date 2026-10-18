"""Configuration.

Values come from explicit arguments, environment variables (``PRISM_*``) and documented
defaults, in that order of precedence. The GitHub token is read from the environment only
and is never echoed: ``PrismConfig`` exposes :attr:`PrismConfig.has_github_token` for
logging instead of the value.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from prism.core.exceptions import ConfigError
from prism.core.limits import LimitPolicy
from prism.core.redaction import redact
from prism.core.types import Severity

#: Configurable test-file conventions. The defaults follow pytest's own discovery rules
#: so that the least surprising assumption is the default (SPEC.md assumption M-4).
DEFAULT_TEST_GLOBS: tuple[str, ...] = (
    "tests/test_*.py",
    "tests/**/test_*.py",
    "test_*.py",
    "*_test.py",
    "conftest.py",
    "**/conftest.py",
)

DEFAULT_TOKEN_ENV_VARS: tuple[str, ...] = ("PRISM_GITHUB_TOKEN", "GITHUB_TOKEN")


def _parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ConfigError("Expected a boolean value.", details={"value": redact(value)})


def _parse_int(value: str, *, name: str) -> int:
    try:
        return int(value.strip())
    except ValueError as exc:
        raise ConfigError(
            "Expected an integer value.", details={"name": name, "value": redact(value)}
        ) from exc


def _parse_float(value: str, *, name: str) -> float:
    try:
        return float(value.strip())
    except ValueError as exc:
        raise ConfigError(
            "Expected a numeric value.", details={"name": name, "value": redact(value)}
        ) from exc


@dataclass(frozen=True)
class PrismConfig:
    """Immutable review configuration."""

    # input limits
    max_diff_bytes: int = 5 * 1024 * 1024
    max_patch_bytes: int = 2 * 1024 * 1024
    max_files: int = 300
    max_response_bytes: int = 8 * 1024 * 1024
    max_pages: int = 100
    max_hunk_lines: int = 20_000
    http_timeout_seconds: float = 20.0
    api_max_body_bytes: int = 5 * 1024 * 1024

    # finding policy
    min_severity: Severity = Severity.INFORMATIONAL
    excluded_rules: tuple[str, ...] = ()
    severity_overrides: Mapping[str, Severity] = field(default_factory=dict)

    # test awareness
    test_file_globs: tuple[str, ...] = DEFAULT_TEST_GLOBS
    coverage_report_path: str | None = None
    max_coverage_bytes: int = 8 * 1024 * 1024

    # optional integrations (all off by default)
    enable_external_tools: bool = False
    external_tool_timeout_seconds: float = 60.0
    enable_llm_extension: bool = False

    # reporting
    include_generated_at: bool = False

    # GitHub
    github_token: str | None = None
    github_api_base: str = "https://api.github.com"
    include_deleted_files: bool = False

    def __post_init__(self) -> None:
        if self.max_diff_bytes <= 0 or self.max_patch_bytes <= 0:
            raise ConfigError("Byte limits must be positive.")
        if self.max_files <= 0:
            raise ConfigError("max_files must be positive.")
        if self.http_timeout_seconds <= 0:
            raise ConfigError("http_timeout_seconds must be positive.")
        try:
            Severity(self.min_severity)
        except ValueError as exc:
            raise ConfigError(
                "Unknown minimum severity.", details={"value": str(self.min_severity)}
            ) from exc

    # ---------------------------------------------------------------- helpers

    @property
    def has_github_token(self) -> bool:
        """Whether a token is configured. The value itself is never exposed."""
        return bool(self.github_token)

    @property
    def limit_policy(self) -> LimitPolicy:
        return LimitPolicy(
            max_diff_bytes=self.max_diff_bytes,
            max_patch_bytes=self.max_patch_bytes,
            max_files=self.max_files,
            max_response_bytes=self.max_response_bytes,
            max_pages=self.max_pages,
            max_hunk_lines=self.max_hunk_lines,
            http_timeout_seconds=self.http_timeout_seconds,
        )

    def with_overrides(self, **changes: Any) -> PrismConfig:
        """Return a copy with validated overrides."""
        unknown = set(changes) - {f.name for f in self.__dataclass_fields__.values()}
        if unknown:
            raise ConfigError("Unknown configuration keys.", details={"keys": sorted(unknown)})
        if changes.get("min_severity") is not None:
            changes["min_severity"] = Severity(changes["min_severity"])
        return replace(self, **changes)

    def safe_summary(self) -> dict[str, Any]:
        """Configuration summary safe to log or return from the API."""
        return {
            "max_diff_bytes": self.max_diff_bytes,
            "max_patch_bytes": self.max_patch_bytes,
            "max_files": self.max_files,
            "max_response_bytes": self.max_response_bytes,
            "max_pages": self.max_pages,
            "http_timeout_seconds": self.http_timeout_seconds,
            "min_severity": Severity(self.min_severity).value,
            "excluded_rules": list(self.excluded_rules),
            "external_tools_enabled": self.enable_external_tools,
            "llm_extension_enabled": self.enable_llm_extension,
            "include_generated_at": self.include_generated_at,
            "github_token_configured": self.has_github_token,
        }

    # ------------------------------------------------------------- factories

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> PrismConfig:
        """Build a configuration from ``PRISM_*`` environment variables."""
        source = dict(os.environ if env is None else env)
        raw: dict[str, Any] = {}

        def take(name: str) -> str | None:
            value = source.get(f"PRISM_{name}")
            return None if value is None or value == "" else value

        if (value := take("MAX_DIFF_BYTES")) is not None:
            raw["max_diff_bytes"] = _parse_int(value, name="MAX_DIFF_BYTES")
        if (value := take("MAX_PATCH_BYTES")) is not None:
            raw["max_patch_bytes"] = _parse_int(value, name="MAX_PATCH_BYTES")
        if (value := take("MAX_FILES")) is not None:
            raw["max_files"] = _parse_int(value, name="MAX_FILES")
        if (value := take("MAX_RESPONSE_BYTES")) is not None:
            raw["max_response_bytes"] = _parse_int(value, name="MAX_RESPONSE_BYTES")
        if (value := take("MAX_PAGES")) is not None:
            raw["max_pages"] = _parse_int(value, name="MAX_PAGES")
        if (value := take("HTTP_TIMEOUT_SECONDS")) is not None:
            raw["http_timeout_seconds"] = _parse_float(value, name="HTTP_TIMEOUT_SECONDS")
        if (value := take("MIN_SEVERITY")) is not None:
            try:
                raw["min_severity"] = Severity(value.strip().lower())
            except ValueError as exc:
                raise ConfigError(
                    "Unknown minimum severity.", details={"value": redact(value)}
                ) from exc
        if (value := take("EXCLUDED_RULES")) is not None:
            raw["excluded_rules"] = tuple(part.strip() for part in value.split(",") if part.strip())
        if (value := take("COVERAGE_REPORT")) is not None:
            raw["coverage_report_path"] = value
        if (value := take("ENABLE_EXTERNAL_TOOLS")) is not None:
            raw["enable_external_tools"] = _parse_bool(value)
        if (value := take("ENABLE_LLM_EXTENSION")) is not None:
            raw["enable_llm_extension"] = _parse_bool(value)
        if (value := take("INCLUDE_GENERATED_AT")) is not None:
            raw["include_generated_at"] = _parse_bool(value)
        if (value := take("GITHUB_API_BASE")) is not None:
            raw["github_api_base"] = value

        token = next((source[name] for name in DEFAULT_TOKEN_ENV_VARS if source.get(name)), None)
        if token:
            raw["github_token"] = token
        return cls(**raw)
