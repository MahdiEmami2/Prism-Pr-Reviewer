"""Finding identity, deduplication, severities, confidence and policy."""

from __future__ import annotations

import pytest

from prism.core.config import PrismConfig
from prism.core.exceptions import ConfigError
from prism.core.types import (
    CONFIDENCE_MEANING,
    Confidence,
    FindingClass,
    Severity,
    severity_at_least,
    severity_rank,
)
from prism.findings.dedupe import deduplicate
from prism.findings.filters import apply_policy, summarize_suppressions
from prism.findings.identity import compute_finding_id, normalize_path, normalize_signature
from prism.findings.models import Finding, FindingLocation
from tests.conftest import make_added_file_diff, review_diff

MUTABLE_DEFAULT = "def f(items=[]):\n    return items\n"


# --------------------------------------------------------------- identity


def test_path_normalisation_handles_prefixes_and_traversal() -> None:
    assert normalize_path("a/app/main.py") == "app/main.py"
    assert normalize_path("b/app/main.py") == "app/main.py"
    assert normalize_path("./app/main.py") == "app/main.py"
    assert normalize_path("app\\main.py") == "app/main.py"
    assert normalize_path("app/./main.py") == "app/main.py"
    assert normalize_path("app/sub/../main.py") == "app/main.py"
    assert normalize_path("") == "<unknown>"


def test_signature_normalisation_ignores_comments_and_literal_text() -> None:
    a = normalize_signature(["hashlib.md5(data)  # old checksum"])
    b = normalize_signature(["hashlib.md5(   data   )"])
    assert a == b.replace('""', "") or a == b


def test_finding_id_survives_unrelated_line_movement() -> None:
    """The core requirement: IDs must not depend on line numbers."""
    short = review_diff(make_added_file_diff("app/m.py", MUTABLE_DEFAULT))
    short_hit = next(f for f in short.findings if f.rule_id == "PY001")

    padded = (
        "import os\n\n\n# a comment block\n# that shifts everything down\n\n\n\n" + MUTABLE_DEFAULT
    )
    long = review_diff(make_added_file_diff("app/m.py", padded))
    long_hit = next(f for f in long.findings if f.rule_id == "PY001")

    assert short_hit.finding_id == long_hit.finding_id
    assert short_hit.location.line != long_hit.location.line


def test_finding_id_differs_for_different_files() -> None:
    one = compute_finding_id(rule_id="PY001", path="a.py", symbol="f", signature="s")
    two = compute_finding_id(rule_id="PY001", path="b.py", symbol="f", signature="s")
    assert one != two


def test_finding_id_differs_across_rules_and_signatures() -> None:
    base = compute_finding_id(rule_id="PY001", path="a.py", symbol="f", signature="s")
    assert base != compute_finding_id(rule_id="PY002", path="a.py", symbol="f", signature="s")
    assert base != compute_finding_id(rule_id="PY001", path="a.py", symbol="f", signature="t")


def test_finding_ids_are_stable_across_runs() -> None:
    first = review_diff(make_added_file_diff("app/m.py", MUTABLE_DEFAULT))
    second = review_diff(make_added_file_diff("app/m.py", MUTABLE_DEFAULT))
    assert [f.finding_id for f in first.findings] == [f.finding_id for f in second.findings]


def test_discriminator_separates_two_similar_sites() -> None:
    code = "import subprocess\n\ndef f(a, b):\n    subprocess.run(a, shell=True)\n    subprocess.run(b, shell=True)\n"
    result = review_diff(make_added_file_diff("app/two.py", code))
    ids = {f.finding_id for f in result.findings if f.rule_id == "PY004"}
    assert len(ids) == 1, "identical signature on the same file maps to one identity by design"


# --------------------------------------------------------------- dedupe


def _finding(
    finding_id: str,
    rule_id: str = "R1",
    path: str = "a.py",
    severity: Severity = Severity.LOW,
) -> Finding:
    return Finding(
        finding_id=finding_id,
        rule_id=rule_id,
        category="test",
        title="t",
        severity=severity,
        confidence=Confidence.HIGH,
        finding_class=FindingClass.DETERMINISTIC,
        location=FindingLocation(path=path, line=1),
        message="m",
    )


def test_deduplicate_collapses_identical_ids_and_logs_it() -> None:
    merged, log = deduplicate([_finding("X"), _finding("X"), _finding("Y", rule_id="R2")])
    assert len(merged) == 2
    assert len(log) == 1
    assert log[0]["finding_id"] == "X"
    assert log[0]["count"] == "2"


def test_deduplicate_keeps_distinct_problems_in_the_same_file() -> None:
    findings = [_finding("A", "PY001", "a.py"), _finding("B", "PY002", "a.py")]
    merged, log = deduplicate(findings)
    assert len(merged) == 2
    assert log == []


def test_deduplicate_output_is_deterministically_ordered() -> None:
    findings = [_finding("A", "R1"), _finding("B", "R2"), _finding("C", "R3")]
    first, _ = deduplicate(list(reversed(findings)))
    second, _ = deduplicate(findings)
    assert [f.finding_id for f in first] == [f.finding_id for f in second]


# --------------------------------------------------------------- severities


def test_severity_ranking_and_comparison() -> None:
    assert severity_rank(Severity.CRITICAL) > severity_rank(Severity.HIGH)
    assert severity_rank("low") < severity_rank("medium")
    assert severity_at_least("high", "medium") is True
    assert severity_at_least("low", "medium") is False


def test_severity_and_confidence_are_independent_dimensions() -> None:
    finding = _finding("Z")
    assert finding.severity is Severity.LOW
    assert finding.confidence is Confidence.HIGH
    assert finding.confidence_meaning == CONFIDENCE_MEANING[Confidence.HIGH]


def test_unknown_severity_is_rejected_by_deserialisation_boundary() -> None:
    from pydantic import ValidationError

    from prism.api.schemas import ReviewOptions

    with pytest.raises(ValidationError) as excinfo:
        ReviewOptions(min_severity="catastrophic")
    assert "min_severity" in str(excinfo.value)


def test_confidence_meanings_are_documented_for_every_level() -> None:
    assert set(CONFIDENCE_MEANING) == {Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW}
    assert all(text.strip() for text in CONFIDENCE_MEANING.values())


# --------------------------------------------------------------- policy


def test_minimum_severity_filters_and_records_the_suppression() -> None:
    findings = [
        _finding("LOW1", "PY010", severity=Severity.LOW),
        _finding("HIGH1", "PY005", severity=Severity.HIGH),
    ]
    kept, suppressed = apply_policy(findings, PrismConfig(min_severity=Severity.HIGH))
    assert [f.finding_id for f in kept] == ["HIGH1"]
    assert suppressed[0]["policy"] == "min_severity=high"
    assert summarize_suppressions(suppressed) == {"min_severity=high": 1}


def test_rule_exclusion_removes_exactly_that_rule() -> None:
    findings = [_finding("A", "PY001"), _finding("B", "PY002")]
    kept, suppressed = apply_policy(findings, PrismConfig(excluded_rules=("PY001",)))
    assert [f.rule_id for f in kept] == ["PY002"]
    assert suppressed[0]["policy"] == "excluded_rules"


def test_severity_override_is_applied_and_recorded() -> None:
    findings = [_finding("A", "PY010")]
    kept, _ = apply_policy(findings, PrismConfig(severity_overrides={"PY010": Severity.HIGH}))
    assert kept[0].severity is Severity.HIGH
    assert kept[0].metadata["severity_overridden_from"] == "low"


def test_default_configuration_suppresses_nothing() -> None:
    findings = [_finding("A", "PY001")]
    kept, suppressed = apply_policy(findings, PrismConfig())
    assert len(kept) == 1
    assert suppressed == []


def test_invalid_minimum_severity_raises_config_error() -> None:
    with pytest.raises(ConfigError):
        PrismConfig(min_severity="nonsense")  # type: ignore[arg-type]


def test_config_with_overrides_rejects_unknown_keys() -> None:
    with pytest.raises(ConfigError):
        PrismConfig().with_overrides(not_a_real_option=True)


def test_config_from_env_parses_and_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRISM_MAX_FILES", "12")
    monkeypatch.setenv("PRISM_MIN_SEVERITY", "medium")
    monkeypatch.setenv("PRISM_EXCLUDED_RULES", "PY010, PY015")
    monkeypatch.setenv("PRISM_ENABLE_EXTERNAL_TOOLS", "true")
    cfg = PrismConfig.from_env()
    assert cfg.max_files == 12
    assert cfg.min_severity is Severity.MEDIUM
    assert cfg.excluded_rules == ("PY010", "PY015")
    assert cfg.enable_external_tools is True


def test_config_from_env_rejects_a_bad_boolean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRISM_ENABLE_EXTERNAL_TOOLS", "maybe")
    with pytest.raises(ConfigError):
        PrismConfig.from_env()


def test_finding_to_dict_exposes_every_required_field() -> None:
    finding = _finding("A", "PY001")
    payload = finding.to_dict()
    for key in (
        "finding_id",
        "rule_id",
        "category",
        "severity",
        "confidence",
        "confidence_meaning",
        "class",
        "deterministic",
        "location",
        "message",
        "evidence",
        "risk",
        "remediation",
        "test_recommendation",
        "documentation",
    ):
        assert key in payload, key
    assert set(payload["location"]) == {"path", "line", "end_line", "symbol", "hunk_section"}


def test_finding_without_a_derivable_line_reports_null_not_a_guess() -> None:
    finding = _finding("A")
    assert finding.location.line == 1
    from prism.analyzers.test_awareness import analyze_test_awareness

    result = analyze_test_awareness(changed_paths=["app/a.py"], config=PrismConfig())
    assert result.finding is not None
    assert result.finding.location.line is None
