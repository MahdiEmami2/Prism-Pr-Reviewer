"""Assert the demonstration project behaves as the sample README claims.

These tests keep the example honest: the risky file must produce a substantial set of
findings, and the cleaned-up file must produce none.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "samples" / "sample_project"


@pytest.fixture(scope="module")
def sample_review():
    from prism.core.config import PrismConfig
    from prism.core.types import ReviewMode
    from prism.diff.parser import parse_unified_diff
    from prism.engine.review import ReviewEngine
    from tests.conftest import make_added_file_diff

    risky = (SAMPLE / "risky_module.py").read_text(encoding="utf-8")
    clean = (SAMPLE / "clean_module.py").read_text(encoding="utf-8")
    # The three testing rules are review-level, not per-file: they compare the whole change
    # set against the test conventions. They are asserted in test_reporting.py and
    # test_coverage.py, so they are excluded here to keep this file about the code rules.
    config = PrismConfig(excluded_rules=("TST001", "TST002", "TST003"))
    engine = ReviewEngine(config)

    def run(code: str, path: str):
        parsed = parse_unified_diff(make_added_file_diff(path, code))
        return engine.analyze(parsed, mode=ReviewMode.DIFF, metadata={"title": path})

    return run(risky, "samples/sample_project/risky_module.py"), run(
        clean, "samples/sample_project/clean_module.py"
    )


def test_risky_sample_triggers_the_expected_rule_set(sample_review) -> None:
    risky_result, _ = sample_review
    rule_ids = {finding.rule_id for finding in risky_result.findings}
    expected = {
        "PY001",  # mutable default
        "PY002",  # bare except
        "PY003",  # swallowed exception
        "PY004",  # shell=True
        "PY005",  # eval
        "PY006",  # pickle
        "PY007",  # unsafe yaml.load
        "PY008",  # os.system
        "PY009",  # tempfile.mktemp
        "PY010",  # md5
        "PY011",  # verify=False
        "PY012",  # unreachable statement
        "PY015",  # assert as validation
        "SEC001",  # hard-coded credential
        "SEC002",  # private key header
    }
    missing = expected - rule_ids
    assert not missing, f"sample did not trigger: {sorted(missing)}"


def test_clean_sample_produces_no_findings(sample_review) -> None:
    _, clean_result = sample_review
    assert clean_result.findings == (), [
        (f.rule_id, f.location.line, f.message) for f in clean_result.findings
    ]
    # The negative control is only meaningful if the same run would have reported something
    # in the risky file, which the companion test asserts.
    assert clean_result.scope.files_analysed >= 1


def test_placeholder_configuration_produces_no_credential_findings() -> None:
    from prism.core.config import PrismConfig
    from prism.core.types import ReviewMode
    from prism.diff.parser import parse_unified_diff
    from prism.engine.review import ReviewEngine
    from tests.conftest import make_added_file_diff

    code = (SAMPLE / "config" / "settings.example.py").read_text(encoding="utf-8")
    parsed = parse_unified_diff(
        make_added_file_diff("samples/sample_project/config/settings.example.py", code)
    )
    config = PrismConfig(excluded_rules=("TST001", "TST002", "TST003"))
    result = ReviewEngine(config).analyze(parsed, mode=ReviewMode.DIFF)
    credential_findings = [f for f in result.findings if f.rule_id in {"SEC001", "SEC003"}]
    assert credential_findings == [], [
        (f.rule_id, f.location.line, f.message) for f in credential_findings
    ]


def test_sample_review_is_labelled_as_demonstration_data() -> None:
    readme = (SAMPLE / "README.md").read_text(encoding="utf-8")
    assert "DEMONSTRATION DATA" in readme
    assert "not real vulnerabilities" in readme


def test_committed_example_reports_exist_and_are_labelled() -> None:
    report = REPO_ROOT / "examples" / "sample_report.md"
    payload = REPO_ROOT / "examples" / "sample_report.json"
    diff_file = REPO_ROOT / "examples" / "sample_diff.patch"
    assert diff_file.is_file(), "run samples/sample_project/generate_diff.sh to produce it"
    assert report.is_file(), "run samples/sample_project/generate_diff.sh to produce it"
    assert payload.is_file(), "run samples/sample_project/generate_diff.sh to produce it"
    text = report.read_text(encoding="utf-8")
    assert "demonstration" in text.lower()
    import json

    data = json.loads(payload.read_text(encoding="utf-8"))
    assert data["metadata"]["demo_data"] is True
    assert data["summary"]["total_findings"] > 0
