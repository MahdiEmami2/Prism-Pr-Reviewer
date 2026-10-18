"""Line-level secret detection with explicit placeholder safeguards.

These rules run on added lines of any text file, because a leaked credential in a YAML or
.properties file matters just as much as one in Python. The safeguards exist so the rules
do not fire on the placeholders that legitimate configuration is full of; the requirement
text explicitly asks for them.
"""

from __future__ import annotations

import re
import string
from collections.abc import Iterable, Sequence

from prism.analyzers.base import AnalysisContext, FindingFactory, RuleSpec
from prism.core.types import Confidence, FindingClass, Severity
from prism.findings.models import Finding

CATEGORY_SECRETS = "secrets"
_DOC = "docs/ANALYSIS_RULES.md"

SPECS: dict[str, RuleSpec] = {
    "SEC001": RuleSpec(
        rule_id="SEC001",
        title="Hard-coded credential",
        category=CATEGORY_SECRETS,
        default_severity=Severity.HIGH,
        default_confidence=Confidence.MEDIUM,
        finding_class=FindingClass.DETERMINISTIC,
        description=(
            "A literal string is assigned to a name that indicates a credential. The "
            "assignment is present in the diff; whether the value is a real secret or a "
            "throwaway test value cannot be proven from the diff alone, so confidence is "
            "medium rather than high."
        ),
        remediation=(
            "Read the value from the environment or a secret manager, and rotate the exposed "
            "credential if it was ever committed."
        ),
        test_recommendation="Add a test that fails when the secret is absent from settings.",
        documentation=_DOC,
        languages=("text", "python", "yaml", "properties"),
    ),
    "SEC002": RuleSpec(
        rule_id="SEC002",
        title="Private key material in source",
        category=CATEGORY_SECRETS,
        default_severity=Severity.CRITICAL,
        default_confidence=Confidence.HIGH,
        finding_class=FindingClass.DETERMINISTIC,
        description=(
            "A PEM private key header appears in an added line. Key material in a source "
            "tree is readable by everyone with repository access, and the header itself is "
            "unambiguous evidence."
        ),
        remediation="Remove the key, rotate it, and load it from a secret store at runtime.",
        documentation=_DOC,
        languages=("text",),
    ),
    "SEC003": RuleSpec(
        rule_id="SEC003",
        title="High-entropy literal next to a secret-like name",
        category=CATEGORY_SECRETS,
        default_severity=Severity.MEDIUM,
        default_confidence=Confidence.LOW,
        finding_class=FindingClass.HEURISTIC,
        description=(
            "A long random-looking literal sits next to a secret-like name. Entropy is a "
            "correlation, not proof: build hashes, base64 fixtures and sample data look the "
            "same, so this finding is a review prompt only."
        ),
        remediation=(
            "Confirm whether the value is a real credential; if it is, move it to a secret store."
        ),
        documentation=_DOC,
        languages=("text",),
    ),
}

_CREDENTIAL_NAMES: tuple[str, ...] = (
    r"pass(?:word|wd|phrase)",
    r"secret",
    r"api[_-]?key",
    r"access[_-]?key",
    r"private[_-]?key",
    r"auth[_-]?token",
    r"client[_-]?secret",
    r"token",
    r"credential",
    r"conn(?:ection)?[_-]?string",
)

_KEY_CORE = "(?:" + "|".join(_CREDENTIAL_NAMES) + ")"
# The prefix is allowed to be empty so that a bare `token = "..."` also matches.
_KEY = r"[A-Za-z0-9_.\-]*" + _KEY_CORE + r"[A-Za-z0-9_.\-]*"

_ASSIGNMENT_RE = re.compile(
    r"(?ix)"
    r"(?P<key>" + _KEY + r")"
    r"\s*(?P<op>[:=])\s*"
    r"(?P<quote>[\"'])(?P<value>[^\"'\n]{0,400})(?P=quote)"
)

_SECRET_HINT_RE = re.compile(r"(?i)(?:^|[_.\-\s])" + _KEY_CORE + r"(?:$|[_.\-\s:=])")

#: Values that are obviously not secrets.
_PLACEHOLDER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)^(?:change[_-]?me|changeme|placeholder|replace[_-]?me|redacted)$"),
    re.compile(
        r"(?i)^(?:example|dummy|sample|fake|test|testing|dev|development|local)"
        r"(?:[_-].*)?$"
    ),
    re.compile(r"(?i)^(?:your|my|the)[_-]"),
    re.compile(r"(?i)(?:^|[_\-\s])(?:here|goes[_-]?here|todo|fixme|tbd)(?:$|[_\-\s])"),
    re.compile(r"^<.*>$"),
    re.compile(r"^\{.*\}$"),
    re.compile(r"^\$\{?[A-Za-z_][A-Za-z0-9_]*\}?$"),
    re.compile(r"^%[sdv]?$"),
    re.compile(r"^(?:x{3,}|\*{3,}|\.{3,}|-{3,}|0{4,}|1{4,}|1234567890?)$"),
    re.compile(r"(?i)^(?:none|null|nil|empty|unset|missing|not[_-]?set)$"),
)

_ENV_LOOKUP_MARKERS: tuple[str, ...] = (
    "os.environ",
    "os.getenv",
    "getenv(",
    "config.get(",
    "settings.",
    "secretmanager",
    "vault",
)

_PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")

_ENTROPY_RE = re.compile(r"^[A-Za-z0-9+/=_\-]{24,}$")


def _has_sequential_run(text: str, minimum: int = 4) -> bool:
    """True when the value contains a run of consecutive alphabet or digit characters.

    ``abcdefghij`` and ``1234567890`` are canonical placeholder shapes; a random token of
    the same length essentially never contains four consecutive sequence characters, which
    is why this is safe to use as a negative filter.
    """
    lowered = text.lower()
    for source in (string.ascii_lowercase, string.digits):
        for start in range(len(source) - minimum + 1):
            window = source[start : start + minimum]
            if window in lowered or window[::-1] in lowered:
                return True
    return False


def is_placeholder(value: str) -> bool:
    """True when a candidate value is recognisably not a real secret.

    Public so the safeguard itself can be unit-tested as a first-class behaviour.
    """
    text = value.strip()
    if not text:
        return True
    if len(text) < 8:
        return True
    if len(set(text)) <= 2:
        return True
    for pattern in _PLACEHOLDER_PATTERNS:
        if pattern.search(text):
            return True
    lowered = text.lower()
    if any(marker.lower() in lowered for marker in _ENV_LOOKUP_MARKERS):
        return True
    if text.isdigit():
        return True
    return _has_sequential_run(text)


def _shannon_entropy(text: str) -> float:
    from math import log2

    if not text:
        return 0.0
    counts: dict[str, int] = {}
    for char in text:
        counts[char] = counts.get(char, 0) + 1
    total = len(text)
    return -sum((count / total) * log2(count / total) for count in counts.values())


def entropy_is_secret_like(value: str) -> bool:
    """Heuristic entropy test used only by the low-confidence SEC003 rule."""
    if not _ENTROPY_RE.match(value):
        return False
    if len(value) < 24:
        return False
    return _shannon_entropy(value) >= 3.5


def _mask(value: str) -> str:
    """Render a candidate without reproducing the whole secret in the report."""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def _mask_line(line: str) -> str:
    if len(line) <= 200:
        return line
    return line[:200] + " ...[line truncated]"


class SecretPatternAnalyzer:
    """Scans added lines for credential-shaped literals."""

    name = "secret_patterns"

    def rule_specs(self) -> Sequence[RuleSpec]:
        return tuple(SPECS.values())

    def analyze(self, context: AnalysisContext) -> Iterable[Finding]:
        factory = FindingFactory(context)
        for lineno in sorted(context.added_lines):
            content = context.added_lines[lineno]
            if _PRIVATE_KEY_RE.search(content):
                yield factory.create(
                    SPECS["SEC002"],
                    line=lineno,
                    message="Added line contains PEM private key material.",
                    signature="pem-private-key",
                    evidence=(_mask_line(content),),
                )
                continue

            matched_credential = False
            for match in _ASSIGNMENT_RE.finditer(content):
                key = match.group("key")
                value = match.group("value")
                if is_placeholder(value):
                    continue
                matched_credential = True
                yield factory.create(
                    SPECS["SEC001"],
                    line=lineno,
                    message=(
                        f"Literal value assigned to credential-like name '{key}' ({_mask(value)})."
                    ),
                    signature=f"{key}=literal",
                    evidence=(_mask_line(content),),
                    symbol=key,
                    metadata={"name": key, "value_length": len(value)},
                )
            if matched_credential:
                continue

            if _SECRET_HINT_RE.search(content):
                for literal in re.findall(r"""["']([^"'\n]{24,})["']""", content):
                    if is_placeholder(literal) or not entropy_is_secret_like(literal):
                        continue
                    yield factory.create(
                        SPECS["SEC003"],
                        line=lineno,
                        message="Long random-looking literal near a secret-like name.",
                        signature=f"entropy:{_mask(literal)}",
                        evidence=(_mask_line(content),),
                    )


__all__ = [
    "SPECS",
    "SecretPatternAnalyzer",
    "entropy_is_secret_like",
    "is_placeholder",
]
