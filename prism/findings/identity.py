"""Stable finding identity and signature normalisation.

Identity must survive code movement, so it deliberately does **not** use line numbers.
Instead it hashes:

* the rule ID,
* the normalised file path,
* the affected symbol when one is known (function/class qualified name),
* a normalised signature derived from the finding's own evidence.

The result is a short, reproducible hex digest. Two runs over the same diff produce the
same IDs; inserting unrelated lines above the finding does not change its ID; and the same
problem reported by two different rules keeps two different IDs.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

_WHITESPACE = re.compile(r"\s+")
_NON_IDENT = re.compile(r"[^0-9a-zA-Z_.:/\-]+")
_ID_LENGTH = 16

#: Path segments that add no information for identity purposes.
_VOLATILE_SEGMENTS = ("/./",)


def normalize_path(path: str) -> str:
    """Normalise a repository-relative path.

    Backslashes become forward slashes, a leading ``./`` or ``a/``/``b/`` diff prefix is
    removed, and traversal segments are collapsed. The result is comparable across
    platforms and across the two sides of a diff.
    """
    if not path:
        return "<unknown>"
    text = path.replace("\\", "/").strip()
    for segment in _VOLATILE_SEGMENTS:
        text = text.replace(segment, "/")
    while text.startswith("./"):
        text = text[2:]
    for prefix in ("a/", "b/"):
        if text.startswith(prefix) and not text.startswith(prefix + prefix):
            text = text[len(prefix) :]
            break
    parts: list[str] = []
    for part in text.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts) or "<unknown>"


def normalize_signature(parts: Iterable[str]) -> str:
    """Collapse evidence into a whitespace- and quote-insensitive signature.

    Comment text, string-literal content and incidental spacing are removed so that a
    reflowed line keeps the same signature, while a genuinely different statement does not.
    """
    joined = " ".join(part for part in parts if part)
    text = re.sub(r"#.*$", "", joined, flags=re.MULTILINE)
    text = re.sub(r'"""(?:.|\n)*?"""', '""', text)
    text = re.sub(r"'''(?:.|\n)*?'''", "''", text)
    text = re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)
    text = re.sub(r"'(?:[^'\\]|\\.)*'", "''", text)
    text = _WHITESPACE.sub(" ", text).strip()
    text = _NON_IDENT.sub("", text)
    return text[:512]


def compute_finding_id(
    *,
    rule_id: str,
    path: str,
    symbol: str | None,
    signature: str,
    discriminator: str | None = None,
) -> str:
    """Return the deterministic finding ID.

    ``discriminator`` distinguishes genuinely different occurrences of the same rule on
    the same symbol (for example two separate ``shell=True`` call sites). It must be
    derived from stable content, never from a line number or a counter.
    """
    payload = "|".join(
        [
            rule_id.strip(),
            normalize_path(path),
            (symbol or "").strip(),
            normalize_signature([signature]),
            (discriminator or "").strip(),
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()
    return f"{rule_id}-{digest[:_ID_LENGTH]}"
