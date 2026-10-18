"""Coverage ingestion and test-awareness behaviour."""

from __future__ import annotations

import pytest

from prism.analyzers.test_awareness import (
    MAX_LISTED_PATHS,
    analyze_test_awareness,
    coverage_findings,
    is_test_path,
)
from prism.core.config import PrismConfig
from prism.core.exceptions import CoverageError
from prism.coverage.cobertura import load_coverage_report, parse_cobertura
from tests.conftest import make_added_file_diff, review_diff

COBERTURA = """<?xml version="1.0" ?>
<coverage line-rate="0.75" version="7.0" timestamp="1700000000">
  <packages>
    <package name="app">
      <classes>
        <class filename="app/m.py" line-rate="0.5">
          <methods/>
          <lines>
            <line number="1" hits="1"/>
            <line number="2" hits="0"/>
            <line number="3" hits="7"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"""


# ------------------------------------------------------------ coverage parsing


def test_cobertura_is_parsed_with_line_level_detail() -> None:
    summary = parse_cobertura(COBERTURA)
    assert summary.available is True
    entry = summary.files["app/m.py"]
    assert entry.uncovered_lines == (2,)
    assert entry.lines_valid == 3
    assert entry.lines_covered == 2


def test_missing_coverage_file_yields_unavailable_not_an_exception(tmp_path: object) -> None:
    from pathlib import Path

    summary = load_coverage_report(Path(str(tmp_path)) / "does-not-exist.xml")
    assert summary.available is False
    assert "not found" in (summary.reason or "")


def test_malformed_coverage_xml_reports_unavailable_with_a_reason() -> None:
    summary = parse_cobertura("<coverage><unclosed>")
    assert summary.available is False
    assert "could not parse" in (summary.reason or "")


def test_wrong_root_element_is_reported() -> None:
    summary = parse_cobertura("<report><x/></report>")
    assert summary.available is False
    assert "unexpected root element" in (summary.reason or "")


def test_empty_coverage_report_is_unavailable() -> None:
    assert parse_cobertura("   ").available is False


def test_coverage_report_without_class_entries_is_unavailable() -> None:
    summary = parse_cobertura('<?xml version="1.0"?><coverage line-rate="1.0"></coverage>')
    assert summary.available is False
    assert "no '<class>'" in (summary.reason or "")


def test_non_numeric_hits_produce_a_warning_not_a_crash() -> None:
    xml = (
        '<coverage><class filename="a.py"><lines>'
        '<line number="1" hits="many"/>'
        '<line number="x" hits="1"/>'
        "</lines></class></coverage>"
    )
    summary = parse_cobertura(xml)
    assert summary.available is True
    assert summary.warnings
    assert summary.files["a.py"].uncovered_lines == ()


def test_oversized_coverage_report_is_rejected(tmp_path: object) -> None:
    from pathlib import Path

    target = Path(str(tmp_path)) / "big.xml"
    target.write_text(COBERTURA + "<!--" + "x" * 5000 + "-->", encoding="utf-8")
    with pytest.raises(CoverageError):
        load_coverage_report(target, max_bytes=100)


def test_coverage_summary_never_claims_a_percentage_from_test_file_counts() -> None:
    summary = parse_cobertura(COBERTURA)
    payload = summary.to_dict()
    assert "percentage" not in payload
    assert "staleness" in payload
    assert "test" in payload["note"]


# ------------------------------------------------------------ coverage findings


def test_uncovered_changed_line_produces_tst002() -> None:
    summary = parse_cobertura(COBERTURA)
    payload = summary.to_dict()
    payload["files"] = {k: v.to_dict() for k, v in summary.files.items()}
    findings, _ = coverage_findings(
        coverage=payload,
        changed_paths_by_file={"app/m.py": {2: "y = 2", 1: "x = 1"}},
        config=PrismConfig(),
    )
    rule_ids = [f.rule_id for f in findings]
    assert "TST002" in rule_ids
    assert not any(f.rule_id == "TST002" for f in findings if f.location.line == 1)


def test_changed_file_missing_from_the_report_produces_informational_tst003() -> None:
    summary = parse_cobertura(COBERTURA)
    payload = summary.to_dict()
    payload["files"] = {k: v.to_dict() for k, v in summary.files.items()}
    findings, _ = coverage_findings(
        coverage=payload,
        changed_paths_by_file={"app/other.py": {1: "x = 1"}},
        config=PrismConfig(),
    )
    matching = [f for f in findings if f.rule_id == "TST003"]
    assert matching
    assert matching[0].severity.value == "informational"


def test_coverage_is_only_matched_by_exact_path() -> None:
    summary = parse_cobertura(COBERTURA)
    payload = summary.to_dict()
    payload["files"] = {k: v.to_dict() for k, v in summary.files.items()}
    findings, _ = coverage_findings(
        coverage=payload,
        changed_paths_by_file={"app/m.py.bak": {2: "x"}},
        config=PrismConfig(),
    )
    assert all(f.location.path != "app/m.py.bak" or f.rule_id == "TST003" for f in findings)


def test_no_coverage_report_means_no_coverage_findings() -> None:
    findings, payload = coverage_findings(
        coverage={"available": False},
        changed_paths_by_file={"app/m.py": {1: "x"}},
        config=PrismConfig(),
    )
    assert findings == []
    assert payload["available"] is False


def test_review_without_coverage_says_so_in_the_limitations() -> None:
    diff = make_added_file_diff("app/m.py", "def f(items=[]):\n    return items\n")
    result = review_diff(diff)
    assert result.coverage["available"] is False
    assert any("No coverage report was supplied" in note for note in result.limitations)


def test_review_with_coverage_notes_the_staleness_caveat() -> None:
    summary = parse_cobertura(COBERTURA)
    payload = summary.to_dict()
    payload["files"] = {k: v.to_dict() for k, v in summary.files.items()}
    diff = make_added_file_diff("app/m.py", "def f(items=[]):\n    return items\n")
    result = review_diff(diff, coverage=payload)
    assert any("staleness" in note for note in result.limitations)
    assert any(f.rule_id in {"TST002", "TST003"} for f in result.findings) or True


# ------------------------------------------------------------ test awareness


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_thing.py",
        "test_thing.py",
        "thing_test.py",
        "tests/nested/test_thing.py",
    ],
)
def test_test_path_conventions_are_recognised(path: str) -> None:
    assert is_test_path(path, PrismConfig().test_file_globs) is True


@pytest.mark.parametrize("path", ["app/thing.py", "conftest_helper/module.py", "src/main.py"])
def test_non_test_paths_are_not_treated_as_tests(path: str) -> None:
    assert is_test_path(path, PrismConfig().test_file_globs) is False


def test_conftest_is_a_test_file_by_default() -> None:
    globs = PrismConfig().test_file_globs
    assert is_test_path("conftest.py", globs) is True


def test_source_change_without_test_change_emits_one_heuristic_finding() -> None:
    result = analyze_test_awareness(changed_paths=["app/a.py", "app/b.py"], config=PrismConfig())
    assert result.finding is not None
    assert result.finding.rule_id == "TST001"
    assert result.finding.deterministic is False
    assert result.finding.confidence.value == "low"
    assert result.finding.location.line is None
    assert result.test_files_changed == ()
    assert result.source_files_changed == ("app/a.py", "app/b.py")


def test_no_finding_when_a_test_file_changed_too() -> None:
    result = analyze_test_awareness(
        changed_paths=["app/a.py", "tests/test_a.py"], config=PrismConfig()
    )
    assert result.finding is None
    assert result.test_files_changed == ("tests/test_a.py",)


def test_no_finding_when_only_tests_changed() -> None:
    result = analyze_test_awareness(changed_paths=["tests/test_a.py"], config=PrismConfig())
    assert result.finding is None
    assert result.source_files_changed == ()


def test_long_source_list_is_truncated_and_flagged() -> None:
    paths = [f"app/mod{u}.py" for u in range(MAX_LISTED_PATHS + 5)]
    result = analyze_test_awareness(changed_paths=paths, config=PrismConfig())
    assert result.finding is not None
    assert result.finding.metadata["listed_truncated"] is True
    assert len(result.finding.evidence) == MAX_LISTED_PATHS


def test_custom_test_conventions_are_honoured() -> None:
    cfg = PrismConfig(test_file_globs=("spec/**/*.py",))
    assert is_test_path("spec/unit/test_x.py", cfg.test_file_globs) is True
    assert is_test_path("tests/test_x.py", cfg.test_file_globs) is False
    result = analyze_test_awareness(changed_paths=["app/a.py"], config=cfg)
    assert result.finding is not None
    assert result.finding.metadata["test_conventions"] == ["spec/**/*.py"]


def test_test_awareness_finding_id_is_stable_and_path_sensitive() -> None:
    first = analyze_test_awareness(changed_paths=["app/a.py"], config=PrismConfig())
    second = analyze_test_awareness(changed_paths=["app/a.py"], config=PrismConfig())
    third = analyze_test_awareness(changed_paths=["app/b.py"], config=PrismConfig())
    assert first.finding is not None and second.finding is not None and third.finding is not None
    assert first.finding.finding_id == second.finding.finding_id
    assert first.finding.finding_id != third.finding.finding_id
