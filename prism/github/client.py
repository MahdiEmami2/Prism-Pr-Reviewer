"""Read-only GitHub REST client.

Behaviour required by the requirement text, and how it is met here:

* **Public PRs work without a token.** No ``Authorization`` header is sent when no token is
  configured.
* **Optional token from the environment.** ``PrismConfig.github_token`` comes from
  ``PRISM_GITHUB_TOKEN`` or ``GITHUB_TOKEN``. The token is placed in the request header and
  nowhere else: it is never logged, never included in an error detail, and never stored on
  the response objects.
* **Read-only.** Only ``GET`` is issued. There is no method that writes.
* **Pagination** follows the ``Link: rel="next"`` header and stops at ``max_pages``.
* **Rate limits** are detected from the status code and headers and raised as a typed error
  carrying the reset instant.
* **Timeouts and response-size caps** are enforced before the body is parsed.
* **Missing patches, binary files, deleted files** are recorded, not assumed away.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from prism.core.config import PrismConfig
from prism.core.exceptions import (
    GitHubAuthError,
    GitHubError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubResponseTooLargeError,
    InputValidationError,
    PaginationLimitError,
)
from prism.core.logging_setup import get_logger
from prism.github.urls import RepoTarget, build_api_url, validate_api_base, validate_ref

logger = get_logger("github")

ACCEPT_PR_JSON = "application/vnd.github+json"
API_VERSION = "2022-11-28"
USER_AGENT = "PRISM-PR-Reviewer"


@dataclass(frozen=True)
class RateLimitState:
    """Rate-limit headers, parsed defensively."""

    limit: int | None = None
    remaining: int | None = None
    reset_epoch: int | None = None
    retry_after: int | None = None

    @classmethod
    def from_headers(cls, headers: Mapping[str, str]) -> RateLimitState:
        def as_int(name: str) -> int | None:
            raw = headers.get(name) or headers.get(name.title())
            if raw is None:
                return None
            try:
                return int(str(raw).strip())
            except ValueError:
                return None

        return cls(
            limit=as_int("x-ratelimit-limit"),
            remaining=as_int("x-ratelimit-remaining"),
            reset_epoch=as_int("x-ratelimit-reset"),
            retry_after=as_int("retry-after"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "limit": self.limit,
            "remaining": self.remaining,
            "reset_epoch": self.reset_epoch,
            "retry_after": self.retry_after,
        }


@dataclass(frozen=True)
class GitHubFileEntry:
    """One entry of the pull-request files listing."""

    filename: str
    status: str
    additions: int = 0
    deletions: int = 0
    changes: int = 0
    patch: str | None = None
    previous_filename: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @property
    def has_patch(self) -> bool:
        return bool(self.patch)


@dataclass(frozen=True)
class PullRequestInfo:
    """Pull-request metadata PRISM uses for the report header."""

    owner: str
    repo: str
    number: int
    title: str
    state: str
    draft: bool
    base_ref: str
    head_ref: str
    head_sha: str
    base_sha: str
    changed_files: int
    additions: int
    deletions: int
    commits: int
    html_url: str
    author: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def to_metadata(self) -> dict[str, Any]:
        return {
            "title": f"{self.owner}/{self.repo}#{self.number} — {self.title}",
            "owner": self.owner,
            "repository": f"{self.owner}/{self.repo}",
            "pull_request": self.number,
            "state": self.state,
            "draft": self.draft,
            "author": self.author or "(unknown)",
            "base_ref": self.base_ref,
            "head_ref": self.head_ref,
            "head_sha": self.head_sha,
            "base_sha": self.base_sha,
            "changed_files": self.changed_files,
            "additions": self.additions,
            "deletions": self.deletions,
            "commits": self.commits,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class GitHubClient:
    """Minimal, read-only GitHub REST client built on httpx.

    The httpx client is injectable so tests can supply a ``MockTransport`` and never touch
    the network.
    """

    def __init__(
        self,
        config: PrismConfig | None = None,
        *,
        http_client: Any | None = None,
        transport: Any | None = None,
    ) -> None:
        self.config = config or PrismConfig()
        self.api_base = validate_api_base(self.config.github_api_base)
        self._owns_client = http_client is None
        if http_client is not None:
            self._client = http_client
        else:
            import httpx

            self._client = httpx.Client(
                base_url=self.api_base,
                timeout=self.config.http_timeout_seconds,
                follow_redirects=False,
                headers=self._default_headers(),
                transport=transport,
            )

    # ------------------------------------------------------------------ helpers

    def _default_headers(self) -> dict[str, str]:
        return {
            "Accept": ACCEPT_PR_JSON,
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": USER_AGENT,
        }

    def _auth_headers(self) -> dict[str, str]:
        """Authorization header, only when a token exists. Never logged."""
        if not self.config.github_token:
            return {}
        return {"Authorization": f"Bearer {self.config.github_token}"}

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------ requests

    def _get(self, url: str, *, params: Mapping[str, Any] | None = None) -> tuple[Any, Any]:
        """Perform one GET and return ``(payload, response)``.

        The URL must already have been produced by :mod:`prism.github.urls`.
        """
        request_headers = self._auth_headers()
        try:
            response = self._client.get(
                url,
                params=dict(params) if params else None,
                headers=request_headers or None,
                timeout=self.config.http_timeout_seconds,
            )
        except Exception as exc:
            name = type(exc).__name__
            if name in {"ConnectTimeout", "ReadTimeout", "TimeoutException", "Timeout"}:
                raise GitHubError(
                    "GitHub request timed out.",
                    details={"timeout_seconds": self.config.http_timeout_seconds},
                ) from exc
            raise GitHubError(
                "GitHub request failed at the transport layer.",
                details={"error_type": name},
            ) from exc

        state = RateLimitState.from_headers(dict(response.headers))
        status = response.status_code

        if status in (403, 429):
            if status == 429 or state.remaining == 0 or state.retry_after is not None:
                raise GitHubRateLimitError(
                    "GitHub API rate limit reached.",
                    reset_at=str(state.reset_epoch) if state.reset_epoch else None,
                    retry_after=str(state.retry_after) if state.retry_after else None,
                )
            raise GitHubAuthError(
                "GitHub denied the request (403). A token may be required or may lack "
                "the required read scope.",
                details={"hint": "Set PRISM_GITHUB_TOKEN with read-only repository access."},
            )
        if status == 401:
            raise GitHubAuthError("GitHub rejected the supplied token.")
        if status == 404:
            raise GitHubNotFoundError(
                "GitHub reported that the repository or pull request does not exist or is "
                "not visible without authentication."
            )
        if status >= 500:
            raise GitHubError(
                "GitHub returned a server error.",
                details={"status": status},
            )
        if status >= 400:
            raise GitHubError("GitHub rejected the request.", details={"status": status})

        body = self._read_capped(response)
        if not body.strip():
            return None, response
        try:
            return json.loads(body), response
        except json.JSONDecodeError as exc:
            raise GitHubError(
                "GitHub returned a body that is not valid JSON.",
                details={"status": status},
            ) from exc

    def _read_capped(self, response: Any) -> str:
        """Read the body while enforcing the configured response-size cap."""
        declared = response.headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > self.config.max_response_bytes:
                    raise GitHubResponseTooLargeError(
                        "GitHub response exceeds the configured size limit.",
                        details={
                            "limit": self.config.max_response_bytes,
                            "observed": int(declared),
                            "unit": "bytes",
                        },
                    )
            except ValueError:
                pass
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > self.config.max_response_bytes:
                raise GitHubResponseTooLargeError(
                    "GitHub response exceeds the configured size limit.",
                    details={
                        "limit": self.config.max_response_bytes,
                        "observed": total,
                        "unit": "bytes",
                    },
                )
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8", errors="replace")

    # ------------------------------------------------------------------ endpoints

    def get_pull_request(self, target: RepoTarget) -> PullRequestInfo:
        """Fetch pull-request metadata."""
        if target.pull_number is None:
            raise InputValidationError("A pull request number is required.")
        url = build_api_url(
            self.api_base,
            "repos",
            target.owner,
            target.repo,
            "pulls",
            str(target.pull_number),
        )
        payload, _ = self._get(url)
        if not isinstance(payload, Mapping):
            raise GitHubError("Unexpected GitHub payload for pull request metadata.")
        return _pull_request_info(target, payload)

    def iter_pull_request_files(
        self, target: RepoTarget, *, max_files: int | None = None
    ) -> Iterator[tuple[list[GitHubFileEntry], bool]]:
        """Yield pages of file entries, honouring the ``Link`` header and page cap.

        The boolean in each tuple is ``True`` when the listing was cut short by a limit, so
        the caller can record an honest "incomplete" scope note.
        """
        if target.pull_number is None:
            raise InputValidationError("A pull request number is required.")
        per_page = 100
        page = 1
        collected = 0
        truncated = False

        while True:
            url = build_api_url(
                self.api_base,
                "repos",
                target.owner,
                target.repo,
                "pulls",
                str(target.pull_number),
                "files",
            )
            payload, response = self._get(url, params={"per_page": per_page, "page": page})
            if payload is None:
                break
            if not isinstance(payload, list):
                raise GitHubError("Unexpected GitHub payload for the files listing.")
            entries = [_file_entry(item) for item in payload if isinstance(item, Mapping)]
            collected += len(entries)
            if max_files is not None and collected > max_files:
                entries = entries[: max(0, max_files - (collected - len(entries)))]
                truncated = True
            yield entries, truncated
            if truncated:
                return
            next_url = _next_link(dict(response.headers))
            if not next_url:
                return
            page += 1
            if page > self.config.max_pages:
                raise PaginationLimitError(
                    "Pull request file listing exceeded the configured page limit.",
                    details={"max_pages": self.config.max_pages, "files_seen": collected},
                )

    def get_file_at_ref(self, target: RepoTarget, path: str, ref: str) -> str | None:
        """Fetch a text file's content at a ref (used only when explicitly enabled)."""
        validate_ref(ref)
        if any(token in path for token in ("..", "\x00", "\\")):
            raise InputValidationError("File path contains an illegal character.")
        url = build_api_url(self.api_base, "repos", target.owner, target.repo, "contents", path)
        payload, _ = self._get(url, params={"ref": ref})
        if not isinstance(payload, Mapping):
            return None
        content = payload.get("content")
        encoding = payload.get("encoding")
        if not isinstance(content, str) or encoding != "base64":
            return None
        import base64
        import binascii

        try:
            raw = base64.b64decode(content, validate=False)
        except (binascii.Error, ValueError):
            return None
        if len(raw) > self.config.max_patch_bytes:
            return None
        return raw.decode("utf-8", errors="replace")


def _next_link(headers: Mapping[str, str]) -> str | None:
    """Extract the ``rel="next"`` URL from a Link header."""
    raw = headers.get("link") or headers.get("Link")
    if not raw:
        return None
    for part in raw.split(","):
        segments = part.split(";")
        if len(segments) < 2:
            continue
        url_part = segments[0].strip()
        if not (url_part.startswith("<") and url_part.endswith(">")):
            continue
        if any('rel="next"' in segment or "rel=next" in segment for segment in segments[1:]):
            return url_part[1:-1]
    return None


def _pull_request_info(target: RepoTarget, payload: Mapping[str, Any]) -> PullRequestInfo:
    user = payload.get("user") if isinstance(payload.get("user"), Mapping) else {}
    base = payload.get("base") if isinstance(payload.get("base"), Mapping) else {}
    head = payload.get("head") if isinstance(payload.get("head"), Mapping) else {}
    return PullRequestInfo(
        owner=target.owner,
        repo=target.repo,
        number=target.pull_number or 0,
        title=str(payload.get("title") or ""),
        state=str(payload.get("state") or "unknown"),
        draft=bool(payload.get("draft", False)),
        base_ref=str(base.get("ref") or ""),
        head_ref=str(head.get("ref") or ""),
        head_sha=str(head.get("sha") or ""),
        base_sha=str(base.get("sha") or ""),
        changed_files=int(payload.get("changed_files") or 0),
        additions=int(payload.get("additions") or 0),
        deletions=int(payload.get("deletions") or 0),
        commits=int(payload.get("commits") or 0),
        html_url=str(payload.get("html_url") or ""),
        author=str(user.get("login")) if user.get("login") else None,
        created_at=payload.get("created_at"),
        updated_at=payload.get("updated_at"),
    )


def _file_entry(item: Mapping[str, Any]) -> GitHubFileEntry:
    patch = item.get("patch")
    return GitHubFileEntry(
        filename=str(item.get("filename") or ""),
        status=str(item.get("status") or "unknown"),
        additions=int(item.get("additions") or 0),
        deletions=int(item.get("deletions") or 0),
        changes=int(item.get("changes") or 0),
        patch=patch if isinstance(patch, str) else None,
        previous_filename=(
            str(item.get("previous_filename"))
            if item.get("previous_filename") is not None
            else None
        ),
        raw=item,
    )


def fetch_pull_request(
    owner: str,
    repo: str,
    number: int,
    *,
    config: PrismConfig | None = None,
    transport: Any | None = None,
) -> tuple[PullRequestInfo, list[GitHubFileEntry], list[dict[str, Any]]]:
    """Convenience wrapper: metadata plus the complete, paginated file listing.

    Returns ``(info, files, notes)`` where ``notes`` records truncation or skipped entries
    so the caller can put them in the report's scope section.
    """
    from prism.github.urls import validate_owner, validate_pull_number, validate_repo

    target = RepoTarget(
        owner=validate_owner(owner),
        repo=validate_repo(repo),
        pull_number=validate_pull_number(number),
    )
    notes: list[dict[str, Any]] = []
    entries: list[GitHubFileEntry] = []
    with GitHubClient(config, transport=transport) as client:
        info = client.get_pull_request(target)
        for page_entries, truncated in client.iter_pull_request_files(
            target, max_files=(config or PrismConfig()).max_files
        ):
            entries.extend(page_entries)
            if truncated:
                notes.append(
                    {
                        "reason": "file_limit_reached",
                        "detail": "listing stopped at the configured max_files limit",
                    }
                )
    return info, entries, notes


__all__ = [
    "GitHubClient",
    "GitHubFileEntry",
    "PullRequestInfo",
    "RateLimitState",
    "fetch_pull_request",
]
