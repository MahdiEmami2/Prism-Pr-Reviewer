"""Optional external tools and the shipped example environment file."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from prism.analyzers.external import BANDIT_SPEC, RUFF_SPEC, run_bandit, run_ruff
from prism.core.types import ToolStatus

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_external_tools_are_off_by_default() -> None:
    from prism.core.config import PrismConfig

    assert PrismConfig().enable_external_tools is False


def test_registry_excludes_external_rules_unless_enabled() -> None:
    from prism.analyzers.registry import build_default_registry

    assert "EXT-RUFF" not in build_default_registry().rule_ids()
    assert "EXT-BANDIT" not in build_default_registry().rule_ids()


def test_external_specs_declare_fixed_severities() -> None:
    assert RUFF_SPEC.default_severity.value == "low"
    assert BANDIT_SPEC.default_severity.value == "medium"


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff is not installed here")
def test_ruff_adapter_reports_findings_with_a_real_exit_code(tmp_path: Path) -> None:
    target = tmp_path / "sample.py"
    target.write_text("import os\n\n\nx = 1\n", encoding="utf-8")
    result = run_ruff(str(target), timeout=60)
    assert result.report.exit_code in (0, 1)
    assert result.report.status in {ToolStatus.FINDINGS.value, ToolStatus.OK.value}
    assert result.report.version is not None
    for finding in result.findings:
        assert finding.rule_id == "EXT-RUFF"
        assert finding.metadata["tool"] == "ruff"


@pytest.mark.skipif(shutil.which("bandit") is None, reason="bandit is not installed here")
def test_bandit_adapter_maps_severity_and_reports_its_exit_code(tmp_path: Path) -> None:
    target = tmp_path / "sample.py"
    target.write_text("import subprocess\n\nsubprocess.run('ls', shell=True)\n", encoding="utf-8")
    result = run_bandit(str(target), timeout=60)
    assert result.report.exit_code in (0, 1)
    assert result.report.version is not None
    assert any(finding.rule_id == "EXT-BANDIT" for finding in result.findings)
    for finding in result.findings:
        assert finding.severity.value in {"low", "medium", "high"}


def test_missing_executable_is_reported_as_unavailable_not_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    target = tmp_path / "sample.py"
    target.write_text("x = 1\n", encoding="utf-8")
    for runner, name in ((run_ruff, "ruff"), (run_bandit, "bandit")):
        result = runner(str(target))
        assert result.report.status == ToolStatus.UNAVAILABLE.value
        assert result.findings == ()
        assert name in (result.report.detail or "")


def test_unexpected_exit_code_is_reported_as_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tool that crashes must surface as a failure, never as silent success."""
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(
        "prism.analyzers.external._run", lambda args, timeout: (2, "", "boom", None)
    )
    target = tmp_path / "sample.py"
    target.write_text("x = 1\n", encoding="utf-8")
    result = run_ruff(str(target))
    assert result.report.status == ToolStatus.FAILED.value
    assert result.report.exit_code == 2
    assert "boom" in (result.report.detail or "")


def test_unparseable_tool_output_is_reported_as_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(
        "prism.analyzers.external._run",
        lambda args, timeout: (
            (1, "this is not json", "", None) if "check" in args else (0, "ruff 1.0", "", None)
        ),
    )
    target = tmp_path / "sample.py"
    target.write_text("x = 1\n", encoding="utf-8")
    result = run_ruff(str(target))
    assert result.report.status == ToolStatus.FAILED.value
    assert "JSON" in (result.report.detail or "")


def test_tool_timeout_is_reported_as_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(
        "prism.analyzers.external._run",
        lambda args, timeout: (-1, "", "", "timeout after 5s"),
    )
    target = tmp_path / "sample.py"
    target.write_text("x = 1\n", encoding="utf-8")
    result = run_ruff(str(target))
    assert result.report.status == ToolStatus.TIMEOUT.value


def test_tool_reports_are_rendered_in_the_markdown_report() -> None:
    from prism.core.config import PrismConfig
    from prism.core.types import ReviewMode
    from prism.diff.parser import parse_unified_diff
    from prism.engine.review import ReviewEngine
    from prism.findings.models import ToolReport
    from prism.reporting.markdown import render_markdown
    from tests.conftest import make_added_file_diff

    parsed = parse_unified_diff(make_added_file_diff("app/m.py", "x = 1\n"))
    engine = ReviewEngine(PrismConfig())
    result = engine.analyze(
        parsed,
        mode=ReviewMode.DIFF,
        tools=[ToolReport(name="ruff", status="unavailable", detail="not installed")],
    )
    report = render_markdown(result)
    assert "ruff" in report
    assert "unavailable" in report


# --------------------------------------------------------------- .env.example


def test_env_example_contains_placeholders_only() -> None:
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "PRISM_GITHUB_TOKEN=" in text
    for line in text.splitlines():
        if line.startswith("PRISM_GITHUB_TOKEN="):
            value = line.split("=", 1)[1]
            assert value == "ghp_replace_me_with_a_read_only_token"
    # No line may look like a real credential.
    for pattern in ("ghp_", "github_pat_", "AKIA", "-----BEGIN"):
        for line in text.splitlines():
            if pattern in line:
                assert "replace_me" in line or "BEGIN" not in line, line


def test_example_env_file_parses_into_a_config() -> None:
    from prism.core.config import PrismConfig

    env: dict[str, str] = {}
    for line in (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if value:
            env[key.strip()] = value.strip()
    cfg = PrismConfig.from_env(env)
    assert cfg.max_files == 300
    assert cfg.enable_external_tools is False
    assert cfg.has_github_token is True  # placeholder present, value never exposed
    assert "ghp_" not in json.dumps(cfg.safe_summary())
