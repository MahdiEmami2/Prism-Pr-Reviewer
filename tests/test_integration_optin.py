"""Integration tests that require network access or real credentials.

They are skipped unless ``PRISM_RUN_INTEGRATION=1`` is set, so the standard suite never
touches the internet and never needs a token.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("PRISM_RUN_INTEGRATION") != "1",
        reason="opt-in: set PRISM_RUN_INTEGRATION=1 to run live GitHub checks",
    ),
]


def test_live_public_pull_request_without_a_token() -> None:
    """Fetch a long-lived public pull request with no credential configured."""
    from prism.core.config import PrismConfig

    cfg = PrismConfig(github_token=None)
    from prism.github.client import fetch_pull_request

    info, entries, notes = fetch_pull_request("python", "cpython", 1, config=cfg)
    assert info.number == 1
    assert entries, "expected at least one changed file"
    del notes


def test_live_rate_limit_headers_are_readable() -> None:
    from prism.core.config import PrismConfig
    from prism.github.client import GitHubClient

    with GitHubClient(PrismConfig()) as client:
        payload, response = client._get("https://api.github.com/rate_limit")
    assert isinstance(payload, dict)
    assert response.status_code == 200
