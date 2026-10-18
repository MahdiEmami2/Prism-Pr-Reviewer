"""Shared test fixtures.

The autouse ``_block_network`` fixture makes the safety property testable: the standard
suite runs with outbound TCP connections refused, so a test that accidentally tries to call
GitHub fails loudly instead of silently depending on the internet. GitHub behaviour is
exercised through ``httpx.MockTransport`` instead.
"""

from __future__ import annotations

import socket
from collections.abc import Sequence
from typing import Any

import pytest

from prism.analyzers.registry import RuleRegistry, build_default_registry
from prism.core.config import PrismConfig
from prism.diff.parser import ParsedDiff, parse_unified_diff
from prism.engine.review import ReviewEngine
from prism.findings.models import Finding, ReviewResult

ALLOWED_ADDRESSES = {"127.0.0.1", "::1", "localhost", ""}


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse outbound TCP so no test can depend on the network."""

    real_connect = socket.socket.connect

    def guarded_connect(self: socket.socket, address: Any) -> Any:
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in ALLOWED_ADDRESSES:
            raise AssertionError(
                f"Blocked network connection attempt to {host!r}. "
                "Tests must use httpx.MockTransport; live tests are opt-in under "
                "PRISM_RUN_INTEGRATION=1."
            )
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


def make_added_file_diff(path: str, code: str) -> str:
    """Build a unified diff that adds ``code`` as a new file at ``path``."""
    lines = code.splitlines()
    body = "\n".join("+" + line for line in lines)
    return (
        f"diff --git a/{path} b/{path}\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        f"+++ b/{path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{body}\n"
    )


def make_modified_file_diff(path: str, added: Sequence[str], context: str = "x = 1") -> str:
    """Build a diff that inserts ``added`` into an existing file."""
    body = "\n".join("+" + line for line in added)
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -1,1 +1,{len(added) + 1} @@\n"
        f" {context}\n"
        f"{body}\n"
    )


@pytest.fixture
def config() -> PrismConfig:
    return PrismConfig()


@pytest.fixture
def registry() -> RuleRegistry:
    return build_default_registry()


def review_diff(
    diff_text: str,
    *,
    cfg: PrismConfig | None = None,
    registry: RuleRegistry | None = None,
    coverage: dict[str, Any] | None = None,
) -> ReviewResult:
    """Parse and review a diff with the default configuration."""
    from prism.core.types import ReviewMode

    effective = cfg or PrismConfig()
    reg = registry or build_default_registry(include_external=effective.enable_external_tools)
    parsed: ParsedDiff = parse_unified_diff(
        diff_text,
        max_bytes=effective.max_diff_bytes,
        max_files=effective.max_files,
        max_patch_bytes=effective.max_patch_bytes,
    )
    engine = ReviewEngine(config=effective, registry=reg)
    return engine.analyze(
        parsed,
        mode=ReviewMode.DIFF,
        metadata={"title": "test review"},
        coverage=coverage,
    )


def review_code(code: str, *, path: str = "app/example.py", **kwargs: Any) -> ReviewResult:
    """Review a snippet as a newly added Python file."""
    return review_diff(make_added_file_diff(path, code), **kwargs)


def rules_of(result: ReviewResult) -> list[str]:
    return sorted(finding.rule_id for finding in result.findings)


def findings_for(result: ReviewResult, rule_id: str) -> list[Finding]:
    return [finding for finding in result.findings if finding.rule_id == rule_id]


def has_rule(result: ReviewResult, rule_id: str) -> bool:
    return any(finding.rule_id == rule_id for finding in result.findings)
