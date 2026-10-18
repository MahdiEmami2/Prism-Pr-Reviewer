"""Markdown and report-sanitisation helpers.

Reviewed repository content is untrusted. A code snippet, filename or PR title containing a
backtick fence, an HTML tag, a table pipe or a control character could otherwise restructure
the report or inject markup into whatever renders it. Every untrusted value therefore passes
through one of these functions before it reaches the report text.
"""

from __future__ import annotations

import re
import unicodedata

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+.!|<>~\-])")
_FENCE_RUN = re.compile(r"`{3,}")


def strip_control_chars(text: str) -> str:
    """Remove C0/C1 control characters, keeping tab, newline and carriage return."""
    return _CONTROL_CHARS.sub("", text)


def normalize_unicode(text: str) -> str:
    """Normalise line separators that would otherwise split a report row."""
    text = text.replace("\u2028", " ").replace("\u2029", " ")
    return unicodedata.normalize("NFC", text)


def safe_text(text: object, *, limit: int = 2000, single_line: bool = False) -> str:
    """Sanitise untrusted text for inline inclusion in a report.

    Removes control characters, neutralises HTML tags by escaping their angle brackets,
    collapses newlines when a single line is required, and caps the length.
    """
    raw = "" if text is None else str(text)
    raw = strip_control_chars(normalize_unicode(raw))
    raw = raw.replace("<", "&lt;").replace(">", "&gt;")
    if single_line:
        raw = re.sub(r"\s+", " ", raw).strip()
    if len(raw) > limit:
        raw = raw[:limit] + " ...[truncated]"
    return raw


def escape_markdown(text: object, *, limit: int = 2000) -> str:
    """Escape Markdown metacharacters in untrusted text."""
    return _MD_SPECIAL.sub(r"\\\1", safe_text(text, limit=limit))


def inline_code(text: object, *, limit: int = 500) -> str:
    """Render untrusted text as an inline code span using a fence that cannot be escaped."""
    raw = safe_text(text, limit=limit, single_line=True).replace("`", "'")
    return f"`{raw}`"


def fence_for(text: str, *, minimum: int = 3) -> str:
    """Return a backtick fence longer than any run inside ``text``."""
    longest = 0
    for match in _FENCE_RUN.finditer(text):
        longest = max(longest, len(match.group(0)))
    return "`" * max(minimum, longest + 1)


def code_block(text: str, *, language: str = "text", limit: int = 4000) -> str:
    """Render untrusted text as a fenced code block that the text cannot break out of."""
    body = safe_text(text, limit=limit)
    fence = fence_for(body)
    return f"{fence}{language}\n{body}\n{fence}"


def escape_table_cell(text: object, *, limit: int = 200) -> str:
    """Escape a value for a Markdown table cell (pipes and newlines are structural)."""
    raw = safe_text(text, limit=limit, single_line=True)
    return raw.replace("|", "\\|")


__all__ = [
    "code_block",
    "escape_markdown",
    "escape_table_cell",
    "fence_for",
    "inline_code",
    "normalize_unicode",
    "safe_text",
    "strip_control_chars",
]
