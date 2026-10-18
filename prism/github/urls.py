"""Strict GitHub input validation: hosts, repository identifiers and PR URLs.

The requirement text allows only explicitly supported GitHub hosts and URL shapes. Anything
else is rejected with :class:`InputValidationError`, so a caller can never turn PRISM into a
generic URL fetcher. This module is the single SSRF control point: the HTTP client refuses
any request whose URL was not built from a value that passed through here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from prism.core.exceptions import InputValidationError

#: Exact hostnames PRISM will talk to. No subdomains, no wildcards.
ALLOWED_API_HOSTS: frozenset[str] = frozenset({"api.github.com"})
ALLOWED_WEB_HOSTS: frozenset[str] = frozenset({"github.com", "www.github.com"})

_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,38})$")
_REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
# Git rejects whitespace, control characters, '~', '^', ':', '?', '*', '[' and '\' in
# ref names. The pattern below mirrors that conservatively.
_BRANCH_RE = re.compile(r"^[^\s\x00-\x1f~^:?*\[\\]{1,250}$")

_PR_URL_RE = re.compile(
    r"^https?://(?P<host>[^/]+)/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)/?$"
)


@dataclass(frozen=True)
class RepoTarget:
    """A validated repository/PR reference."""

    owner: str
    repo: str
    pull_number: int | None = None

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"


def validate_owner(owner: str) -> str:
    """Validate a GitHub owner (user or organisation) name."""
    text = (owner or "").strip()
    if not text:
        raise InputValidationError("Repository owner is required.")
    if "/" in text or "\\" in text or ".." in text:
        raise InputValidationError(
            "Repository owner contains an illegal character.",
            details={"hint": "Owner must be a bare GitHub owner name."},
        )
    if not _OWNER_RE.match(text):
        raise InputValidationError("Repository owner has an invalid format.")
    return text


def validate_repo(repo: str) -> str:
    """Validate a GitHub repository name."""
    text = (repo or "").strip()
    if not text:
        raise InputValidationError("Repository name is required.")
    if text.endswith(".git"):
        text = text[:-4]
    if "/" in text or "\\" in text or ".." in text or text in {".", ".."}:
        raise InputValidationError(
            "Repository name contains an illegal character.",
            details={"hint": "Repository must be a bare name, not a path."},
        )
    if not _REPO_RE.match(text):
        raise InputValidationError("Repository name has an invalid format.")
    return text


def validate_pull_number(number: int | str) -> int:
    """Validate a pull-request number."""
    try:
        value = int(str(number).strip())
    except (TypeError, ValueError) as exc:
        raise InputValidationError("Pull request number must be an integer.") from exc
    if value <= 0 or value > 9_999_999:
        raise InputValidationError(
            "Pull request number is out of range.", details={"observed": value}
        )
    return value


def validate_ref(ref: str) -> str:
    """Validate a git ref (branch/sha) used as a query parameter."""
    text = (ref or "").strip()
    if not text:
        raise InputValidationError("A ref must not be empty.")
    if not _BRANCH_RE.match(text):
        raise InputValidationError("Ref contains characters that are not allowed.")
    return text


def validate_api_base(base: str) -> str:
    """Validate the API base URL.

    Only ``https`` and an allow-listed host are accepted, so a misconfigured base cannot
    redirect PRISM at an arbitrary service.
    """
    from urllib.parse import urlparse

    parsed = urlparse((base or "").strip())
    if parsed.scheme != "https":
        raise InputValidationError("GitHub API base URL must use https.")
    if parsed.hostname not in ALLOWED_API_HOSTS:
        raise InputValidationError(
            "GitHub API base URL host is not allow-listed.",
            details={"allowed_hosts": sorted(ALLOWED_API_HOSTS)},
        )
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise InputValidationError("GitHub API base URL must not contain a path or query.")
    return f"https://{parsed.hostname}"


def parse_pull_request_url(url: str) -> RepoTarget:
    """Parse a github.com pull-request URL into a validated target."""
    text = (url or "").strip()
    match = _PR_URL_RE.match(text)
    if not match:
        raise InputValidationError(
            "Not a supported pull request URL.",
            details={"expected_form": "https://github.com/<owner>/<repo>/pull/<number>"},
        )
    host = match.group("host").lower()
    if host not in ALLOWED_WEB_HOSTS:
        raise InputValidationError(
            "URL host is not allow-listed.", details={"allowed_hosts": sorted(ALLOWED_WEB_HOSTS)}
        )
    return RepoTarget(
        owner=validate_owner(match.group("owner")),
        repo=validate_repo(match.group("repo")),
        pull_number=validate_pull_number(match.group("number")),
    )


def build_api_url(api_base: str, *segments: str, query: str | None = None) -> str:
    """Build an absolute API URL from an allow-listed base and pre-validated segments."""
    base = validate_api_base(api_base)
    cleaned: list[str] = []
    for segment in segments:
        piece = str(segment).strip("/")
        if not piece:
            continue
        if any(token in piece for token in ("..", "\x00", "?", "#", "\\")):
            raise InputValidationError("API path segment contains an illegal character.")
        cleaned.append(piece)
    url = base + "/" + "/".join(cleaned)
    if query:
        if any(token in query for token in ("\x00", "#", " ")):
            raise InputValidationError("Query string contains an illegal character.")
        url = f"{url}?{query}"
    from urllib.parse import urlparse

    if urlparse(url).hostname not in ALLOWED_API_HOSTS:
        raise InputValidationError("Constructed URL host is not allow-listed.")
    return url


__all__ = [
    "ALLOWED_API_HOSTS",
    "ALLOWED_WEB_HOSTS",
    "RepoTarget",
    "build_api_url",
    "parse_pull_request_url",
    "validate_api_base",
    "validate_owner",
    "validate_pull_number",
    "validate_ref",
    "validate_repo",
]
