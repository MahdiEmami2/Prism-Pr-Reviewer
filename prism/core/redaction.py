"""Secret and credential redaction.

Used by the logging filter, the API error handlers and the report writers. Redaction is
best-effort defence in depth: the primary control is that PRISM never stores a token in
the first place.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"), "[REDACTED:github_token]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "[REDACTED:github_token]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED:aws_access_key_id]"),
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
        "[REDACTED:private_key]",
    ),
    (re.compile(r"(?i)\b(bearer|token)\s+[A-Za-z0-9._\-]{20,}"), r"\1 [REDACTED]"),
    (re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key)\s*[=:]\s*\S+"), r"\1=[REDACTED]"),
    (re.compile(r"(?i)authorization:\s*\S+"), "authorization: [REDACTED]"),
)

SENSITIVE_ENV_KEYS = (
    "GITHUB_TOKEN",
    "PRISM_GITHUB_TOKEN",
    "GH_TOKEN",
    "GITHUB_PAT",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "DATABASE_URL",
    "PRISM_DATABASE_URL",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)


def redact(text: Any) -> str:
    """Return ``text`` as a string with known secret shapes replaced."""
    if text is None:
        return ""
    out = text if isinstance(text, str) else str(text)
    for pattern, replacement in _PATTERNS:
        out = pattern.sub(replacement, out)
    return out


def is_sensitive_key(key: str) -> bool:
    """True when an environment variable name looks credential-bearing."""
    upper = key.upper()
    if upper in SENSITIVE_ENV_KEYS:
        return True
    return any(token in upper for token in ("TOKEN", "SECRET", "PASSWORD", "API_KEY"))


def redact_mapping(data: Mapping[str, Any]) -> dict[str, str]:
    """Redact every value of a mapping, keeping the keys."""
    return {str(key): redact(value) for key, value in data.items()}


def safe_env_names() -> list[str]:
    """Names of credential-bearing variables that are *set*, never their values."""
    import os

    return sorted(name for name in os.environ if is_sensitive_key(name))
