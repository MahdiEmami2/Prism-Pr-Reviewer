"""GitHub integration: URL validation, pagination, rate limits, missing patches.

Every HTTP call is served by ``httpx.MockTransport``. The autouse network guard in
``conftest`` would fail the suite if a test ever reached the real API.
"""

from __future__ import annotations

import json

import httpx
import pytest

from prism.core.config import PrismConfig
from prism.core.exceptions import (
    GitHubAuthError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubResponseTooLargeError,
    InputValidationError,
    PaginationLimitError,
)
from prism.core.types import ReviewMode
from prism.engine.review import ReviewEngine
from prism.github.client import GitHubClient, RateLimitState
from prism.github.diff_source import files_from_github
from prism.github.urls import (
    build_api_url,
    parse_pull_request_url,
    validate_api_base,
    validate_owner,
    validate_pull_number,
    validate_ref,
    validate_repo,
)
from tests.conftest import review_diff

# --------------------------------------------------------------- URLs


def test_valid_pull_request_url_parses() -> None:
    target = parse_pull_request_url("https://github.com/octocat/Hello-World/pull/1347")
    assert target.owner == "octocat"
    assert target.repo == "Hello-World"
    assert target.pull_number == 1347
    assert target.slug == "octocat/Hello-World"


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example.com/octocat/Hello-World/pull/1",
        "https://api.github.com.evil.test/octocat/Hello-World/pull/1",
        "https://raw.githubusercontent.com/octocat/Hello-World/pull/1",
        "http://127.0.0.1:8000/octocat/Hello-World/pull/1",
        "https://github.com/octocat/Hello-World/issues/1",
        "https://github.com/octocat",
        "file:///etc/passwd",
        "https://github.com/octocat/Hello-World/pull/abc",
    ],
)
def test_unsupported_urls_are_rejected(url: str) -> None:
    with pytest.raises(InputValidationError):
        parse_pull_request_url(url)


@pytest.mark.parametrize("owner", ["../etc", "a/b", "bad owner", "", "-" * 50])
def test_bad_owners_are_rejected(owner: str) -> None:
    with pytest.raises(InputValidationError):
        validate_owner(owner)


@pytest.mark.parametrize("repo", ["../secrets", "a/b", "..", "", "x" * 200])
def test_bad_repo_names_are_rejected(repo: str) -> None:
    with pytest.raises(InputValidationError):
        validate_repo(repo)


def test_repo_name_with_git_suffix_is_normalised() -> None:
    assert validate_repo("Hello-World.git") == "Hello-World"


@pytest.mark.parametrize("number", [0, -1, 10_000_000, "abc"])
def test_bad_pull_numbers_are_rejected(number: object) -> None:
    with pytest.raises(InputValidationError):
        validate_pull_number(number)  # type: ignore[arg-type]


def test_api_base_must_be_https_and_allow_listed() -> None:
    assert validate_api_base("https://api.github.com") == "https://api.github.com"
    for bad in (
        "http://api.github.com",
        "https://api.github.com/v3",
        "https://evil.example.com",
        "https://127.0.0.1",
    ):
        with pytest.raises(InputValidationError):
            validate_api_base(bad)


def test_path_segments_cannot_smuggle_traversal_into_an_api_url() -> None:
    with pytest.raises(InputValidationError):
        build_api_url("https://api.github.com", "repos", "..", "etc", "pulls")
    with pytest.raises(InputValidationError):
        build_api_url("https://api.github.com", "repos", "o", "r?x=1")


def test_ref_validation_rejects_control_characters_and_whitespace() -> None:
    assert validate_ref("feature/thing") == "feature/thing"
    assert validate_ref("v1.2.3-rc1") == "v1.2.3-rc1"
    for bad in ("", "bad ref", "with\x00nul", "x" * 300, "tab\tref", "tilde~ref", "caret^ref"):
        with pytest.raises(InputValidationError):
            validate_ref(bad)


# --------------------------------------------------------------- client


def _transport(routes: dict[str, tuple[int, dict, str]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        key = request.url.path + ("?" + request.url.query.decode() if request.url.query else "")
        for pattern, (status, headers, body) in routes.items():
            if key.startswith(pattern) or request.url.path == pattern:
                return httpx.Response(status, headers=headers, content=body)
        return httpx.Response(404, json={"message": "Not Found"})

    return httpx.MockTransport(handler)


def _client(routes: dict[str, tuple[int, dict, str]], **kwargs: object) -> GitHubClient:
    cfg = PrismConfig(**kwargs)  # type: ignore[arg-type]
    return GitHubClient(cfg, transport=_transport(routes))


def test_pull_request_metadata_is_parsed() -> None:
    payload = {
        "title": "Fix the thing",
        "state": "open",
        "draft": False,
        "user": {"login": "octocat"},
        "base": {"ref": "main", "sha": "aaa"},
        "head": {"ref": "feature", "sha": "bbb"},
        "changed_files": 2,
        "additions": 10,
        "deletions": 3,
        "commits": 2,
        "html_url": "https://github.com/octocat/Hello-World/pull/1",
        "created_at": "2026-01-01T00:00:00Z",
    }
    routes = {"/repos/octocat/Hello-World/pulls/1": (200, {}, json.dumps(payload))}
    with _client(routes) as client:
        info = client.get_pull_request(
            parse_pull_request_url("https://github.com/octocat/Hello-World/pull/1")
        )
    assert info.title == "Fix the thing"
    assert info.author == "octocat"
    assert info.changed_files == 2
    metadata = info.to_metadata()
    assert metadata["repository"] == "octocat/Hello-World"
    assert metadata["pull_request"] == 1


def test_token_is_sent_when_configured_and_absent_when_not() -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"title": "t", "state": "open"})

    target = parse_pull_request_url("https://github.com/o/r/pull/1")
    with GitHubClient(PrismConfig(), transport=httpx.MockTransport(handler)) as anon:
        anon.get_pull_request(target)
    with GitHubClient(
        PrismConfig(github_token="ghp_abcdefghijklmnopqrstuvwxyz012345"),
        transport=httpx.MockTransport(handler),
    ) as authed:
        authed.get_pull_request(target)
    assert seen[0] is None
    assert seen[1] == "Bearer ghp_abcdefghijklmnopqrstuvwxyz012345"


def test_rate_limit_error_carries_the_reset_instant_and_no_token() -> None:
    routes = {
        "/repos/o/r/pulls/1": (
            403,
            {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1800000000"},
            json.dumps({"message": "API rate limit exceeded"}),
        )
    }
    with (
        pytest.raises(GitHubRateLimitError) as excinfo,
        _client(routes, github_token="ghp_abcdefghijklmnopqrstuvwxyz012345") as client,
    ):
        client.get_pull_request(parse_pull_request_url("https://github.com/o/r/pull/1"))
    assert excinfo.value.details["rate_limit_reset"] == "1800000000"
    assert "ghp_" not in json.dumps(excinfo.value.to_dict())


def test_forbidden_without_a_rate_limit_is_an_auth_error_with_guidance() -> None:
    routes = {"/repos/o/r/pulls/1": (403, {"x-ratelimit-remaining": "55"}, json.dumps({}))}
    with pytest.raises(GitHubAuthError) as excinfo, _client(routes) as client:
        client.get_pull_request(parse_pull_request_url("https://github.com/o/r/pull/1"))
    assert "read-only" in str(excinfo.value.details["hint"])
    assert excinfo.value.http_status == 502


def test_unauthorized_and_not_found_map_to_typed_errors() -> None:
    for status, expected in ((401, GitHubAuthError), (404, GitHubNotFoundError)):
        routes = {"/repos/o/r/pulls/1": (status, {}, json.dumps({}))}
        with pytest.raises(expected), _client(routes) as client:
            client.get_pull_request(parse_pull_request_url("https://github.com/o/r/pull/1"))


def test_retry_after_header_is_surfaced() -> None:
    routes = {
        "/repos/o/r/pulls/1": (429, {"retry-after": "60"}, json.dumps({})),
    }
    with pytest.raises(GitHubRateLimitError) as excinfo, _client(routes) as client:
        client.get_pull_request(parse_pull_request_url("https://github.com/o/r/pull/1"))
    assert excinfo.value.details["retry_after_seconds"] == "60"


def test_pagination_follows_the_link_header() -> None:
    page_one = [{"filename": "a.py", "status": "added", "patch": "@@ -0,0 +1,1 @@\n+x = 1\n"}]
    page_two = [
        {"filename": "b.py", "status": "modified", "patch": "@@ -1 +1,2 @@\n y = 1\n+z = 2\n"}
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "1" or request.url.params.get("page") is None:
            return httpx.Response(
                200,
                headers={
                    "link": '<https://api.github.com/repos/o/r/pulls/1/files?page=2>; rel="next"'
                },
                json=page_one,
            )
        return httpx.Response(200, json=page_two)

    target = parse_pull_request_url("https://github.com/o/r/pull/1")
    with GitHubClient(PrismConfig(), transport=httpx.MockTransport(handler)) as client:
        collected = []
        for entries, truncated in client.iter_pull_request_files(target):
            collected.extend(entries)
            assert truncated is False
    assert [entry.filename for entry in collected] == ["a.py", "b.py"]


def test_pagination_stops_at_the_configured_page_cap() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page") or "1")
        return httpx.Response(
            200,
            headers={
                "link": f'<https://api.github.com/repos/o/r/pulls/1/files?page={page + 1}>; rel="next"'
            },
            json=[
                {
                    "filename": f"f{page}.py",
                    "status": "modified",
                    "patch": "@@ -1 +1,2 @@\n a\n+b\n",
                }
            ],
        )

    target = parse_pull_request_url("https://github.com/o/r/pull/1")
    with (
        pytest.raises(PaginationLimitError),
        GitHubClient(PrismConfig(max_pages=3), transport=httpx.MockTransport(handler)) as client,
    ):
        list(client.iter_pull_request_files(target))


def test_file_limit_truncates_the_listing_and_says_so() -> None:
    payload = [
        {"filename": f"f{i}.py", "status": "added", "patch": "@@ -0,0 +1,1 @@\n+x = 1\n"}
        for i in range(5)
    ]
    routes = {"/repos/o/r/pulls/1/files": (200, {}, json.dumps(payload))}
    target = parse_pull_request_url("https://github.com/o/r/pull/1")
    with _client(routes) as client:
        collected = []
        truncated_flags = []
        for entries, truncated in client.iter_pull_request_files(target, max_files=2):
            collected.extend(entries)
            truncated_flags.append(truncated)
    assert len(collected) == 2
    assert truncated_flags[-1] is True


def test_oversized_json_response_is_rejected_before_parsing() -> None:
    big = json.dumps({"title": "x" * 1000, "state": "open"})
    routes = {"/repos/o/r/pulls/1": (200, {"content-length": str(len(big))}, big)}
    with (
        pytest.raises(GitHubResponseTooLargeError),
        _client(routes, max_response_bytes=100) as client,
    ):
        client.get_pull_request(parse_pull_request_url("https://github.com/o/r/pull/1"))


def test_non_json_response_is_reported_as_a_github_error() -> None:
    routes = {"/repos/o/r/pulls/1": (200, {}, "not json at all")}
    from prism.core.exceptions import GitHubError

    with pytest.raises(GitHubError), _client(routes) as client:
        client.get_pull_request(parse_pull_request_url("https://github.com/o/r/pull/1"))


def test_rate_limit_state_parsing_tolerates_garbage() -> None:
    state = RateLimitState.from_headers({"x-ratelimit-remaining": "abc", "retry-after": "12"})
    assert state.remaining is None
    assert state.retry_after == 12


# --------------------------------------------------------------- diff source


def test_file_entry_without_a_patch_becomes_a_skipped_record() -> None:
    from prism.github.client import GitHubFileEntry

    entries = [
        GitHubFileEntry(filename="assets/logo.png", status="modified", patch=None),
        GitHubFileEntry(
            filename="app/x.py",
            status="added",
            patch="@@ -0,0 +1,1 @@\n+def f():\n",
        ),
    ]
    parsed = files_from_github(entries)
    assert any(item["reason"] == "no_patch_available" for item in parsed.skipped)
    assert parsed.files[1].path == "app/x.py"


def test_binary_status_is_recorded_as_binary() -> None:
    from prism.github.client import GitHubFileEntry

    entries = [GitHubFileEntry(filename="a.bin", status="binary", patch=None)]
    parsed = files_from_github(entries)
    assert parsed.files[0].is_binary


def test_deleted_file_entry_is_recorded_and_not_analysed() -> None:
    from prism.github.client import GitHubFileEntry

    entries = [
        GitHubFileEntry(
            filename="app/gone.py",
            status="removed",
            patch="@@ -1,2 +0,0 @@\n-a = 1\n-b = 2",
        )
    ]
    parsed = files_from_github(entries)
    assert parsed.files[0].status.value == "deleted"
    assert not parsed.files[0].analyzable
    assert any(item["reason"] == "deleted_file" for item in parsed.skipped)


def test_renamed_file_entry_uses_the_new_path() -> None:
    from prism.github.client import GitHubFileEntry

    entries = [
        GitHubFileEntry(
            filename="app/new_name.py",
            status="renamed",
            previous_filename="app/old_name.py",
            patch="@@ -1,1 +1,2 @@\n a = 1\n+def f(items=[]):\n+    return items",
        )
    ]
    parsed = files_from_github(entries)
    assert parsed.files[0].path == "app/new_name.py"
    assert parsed.files[0].previous_path == "app/old_name.py"


def test_end_to_end_pull_request_review_uses_mocked_transport() -> None:
    """The whole GitHub path, with no network access at all."""
    files_payload = [
        {
            "filename": "app/risky.py",
            "status": "added",
            "patch": (
                "@@ -0,0 +1,5 @@\n"
                "+import subprocess\n"
                "+\n"
                "+def run(cmd):\n"
                "+    subprocess.run(cmd, shell=True)\n"
                "+    return cmd\n"
            ),
        },
        {
            "filename": "assets/logo.bin",
            "status": "binary",
        },
    ]
    metadata_payload = {
        "title": "Add risky helper",
        "state": "open",
        "user": {"login": "octocat"},
        "base": {"ref": "main", "sha": "a"},
        "head": {"ref": "topic", "sha": "b"},
        "changed_files": 2,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json=files_payload)
        return httpx.Response(200, json=metadata_payload)

    target = parse_pull_request_url("https://github.com/octocat/Hello-World/pull/7")
    with GitHubClient(PrismConfig(), transport=httpx.MockTransport(handler)) as client:
        info = client.get_pull_request(target)
        entries = []
        for page, _ in client.iter_pull_request_files(target):
            entries.extend(page)

    parsed = files_from_github(entries)
    engine = ReviewEngine(PrismConfig())
    result = engine.analyze(parsed, mode=ReviewMode.GITHUB, metadata=info.to_metadata())

    rule_ids = {finding.rule_id for finding in result.findings}
    assert "PY004" in rule_ids
    assert "TST001" in rule_ids
    assert any(item["reason"] == "no_patch_available" for item in result.scope.skipped)
    assert result.metadata["repository"] == "octocat/Hello-World"
    assert result.mode == "github_pr"


def test_local_diff_review_and_github_review_agree_on_the_same_code() -> None:
    from prism.github.client import GitHubFileEntry

    patch = "@@ -0,0 +1,2 @@\n+def f(items=[]):\n+    return items\n"
    entries = [GitHubFileEntry(filename="app/same.py", status="added", patch=patch)]
    github_result = ReviewEngine(PrismConfig()).analyze(
        files_from_github(entries), mode=ReviewMode.GITHUB
    )
    local_diff = (
        "diff --git a/app/same.py b/app/same.py\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/app/same.py\n"
        f"{patch}"
    )
    local_result = review_diff(local_diff)
    assert {f.rule_id for f in github_result.findings} == {f.rule_id for f in local_result.findings}
    assert {f.finding_id for f in github_result.findings} == {
        f.finding_id for f in local_result.findings
    }
