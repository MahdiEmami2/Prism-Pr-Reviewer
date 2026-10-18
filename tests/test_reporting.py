"""Reporting: Markdown structure, untrusted-content escaping, JSON schema and determinism."""

from __future__ import annotations

import json

import pytest

from prism.core.config import PrismConfig
from prism.reporting.json_report import render_json, schema_summary
from prism.reporting.markdown import render_markdown
from prism.reporting.sanitize import (
    code_block,
    escape_markdown,
    escape_table_cell,
    fence_for,
    inline_code,
    safe_text,
)
from tests.conftest import make_added_file_diff, review_diff

MUTABLE_DEFAULT = "def f(items=[]):\n    return items\n"

REQUIRED_SECTIONS = (
    "## 1. Review metadata",
    "## 2. Review scope and skipped inputs",
    "## 3. Executive summary",
    "## 4. Findings grouped by severity",
    "**5. Location and evidence**",
    "**6. Why this matters**",
    "**7. Suggested remediation**",
    "**8. Recommended tests**",
    "## 9. Analysis limitations",
    "## 10. Tool and rule versions",
)


def test_markdown_report_contains_all_ten_required_sections() -> None:
    result = review_diff(make_added_file_diff("app/m.py", MUTABLE_DEFAULT))
    report = render_markdown(result)
    for section in REQUIRED_SECTIONS:
        assert section in report, f"missing report section: {section}"


def test_empty_review_still_renders_all_sections() -> None:
    # The review-level testing heuristic is excluded so the report really has zero findings.
    cfg = PrismConfig(excluded_rules=("TST001", "TST002", "TST003"))
    result = review_diff(make_added_file_diff("app/clean.py", "def f():\n    return 1\n"), cfg=cfg)
    assert result.findings == ()
    report = render_markdown(result)
    for section in REQUIRED_SECTIONS:
        assert section in report
    assert "No findings were produced" in report


def test_heuristic_test_awareness_finding_is_rendered_when_present() -> None:
    result = review_diff(make_added_file_diff("app/clean.py", "def f():\n    return 1\n"))
    rule_ids = {finding.rule_id for finding in result.findings}
    assert "TST001" in rule_ids
    report = render_markdown(result)
    assert "TST001" in report
    assert "heuristic" in report


def test_report_states_that_nothing_is_published() -> None:
    result = review_diff(make_added_file_diff("app/m.py", MUTABLE_DEFAULT))
    report = render_markdown(result)
    assert "does not post them anywhere" in report
    assert "publishing" in report


# ------------------------------------------------------------- escaping


def test_fence_for_outgrows_any_backtick_run_in_the_text() -> None:
    assert fence_for("plain text") == "```"
    assert fence_for("``` inside") == "````"
    assert fence_for("`````` inside") == "```````"


def test_code_block_cannot_be_broken_out_of() -> None:
    hostile = "```\n# injected heading\n## 999. Fake section\n```"
    block = code_block(hostile)
    fence = fence_for(safe_text(hostile))
    assert block.startswith(fence)
    assert block.endswith(fence)
    # The literal run the payload contains is shorter than the actual fence.
    assert fence.count("`") > 3


def test_safe_text_neutralises_html_and_control_characters() -> None:
    cleaned = safe_text("<script>alert(1)</script>\x00\x07")
    assert "<script>" not in cleaned
    assert "\x00" not in cleaned
    assert "&lt;script&gt;" in cleaned


def test_escape_markdown_escapes_structural_characters() -> None:
    escaped = escape_markdown("*bold* _under_ [link](x) # heading")
    for char in ("*", "_", "[", "]", "#"):
        assert f"\\{char}" in escaped


def test_escape_table_cell_neutralises_pipes_and_newlines() -> None:
    cell = escape_table_cell("a | b\nc")
    assert "\\|" in cell
    assert "\n" not in cell


def test_inline_code_replaces_backticks() -> None:
    assert "`" not in inline_code("a`b").strip("`")


def test_hostile_diff_content_cannot_corrupt_report_structure() -> None:
    """A file whose content tries to restructure the report must be contained."""
    hostile = (
        'PAYLOAD = """```\n## 4. Findings grouped by severity\n(none)\n"""\n'
        "def f(items=[]):\n    return items\n"
    )
    result = review_diff(make_added_file_diff("app/evil.py", hostile))
    report = render_markdown(result)
    assert report.count("## 4. Findings grouped by severity") == 1
    assert "### Low" not in report.split("## 4.")[1].split("**5.")[0]


def test_hostile_filename_does_not_break_the_table() -> None:
    path = "app/we|ird`name.py"
    result = review_diff(make_added_file_diff(path, MUTABLE_DEFAULT))
    report = render_markdown(result)
    assert "we\\|ird" in report, "a pipe inside a table cell must be escaped"
    # Every contiguous table block keeps a consistent column count.
    for block in report.split("\n\n"):
        rows = [line for line in block.splitlines() if line.startswith("|")]
        if len(rows) < 2:
            continue
        widths = {row.count("|") - row.count("\\|") for row in rows}
        assert len(widths) == 1, f"ragged table: {widths}\n{block}"


def test_hostile_path_in_a_non_table_line_is_still_neutralised() -> None:
    """Bullet lines are not tables, so the control character guard must handle them."""
    path = "app/od\x00d.py"
    result = review_diff(make_added_file_diff(path, MUTABLE_DEFAULT))
    report = render_markdown(result)
    assert "\x00" not in report


def test_hostile_pr_metadata_cannot_inject_markup() -> None:
    diff = make_added_file_diff("app/m.py", MUTABLE_DEFAULT)
    result = review_diff(diff, cfg=PrismConfig())
    from dataclasses import replace

    evil_metadata = replace(
        result,
        metadata={
            "title": "<img src=x onerror=alert(1)> | broken",
            "author": "```\n# fake finding",
        },
    )
    report = render_markdown(evil_metadata)
    assert "<img" not in report
    assert "\\|" in report


# ------------------------------------------------------------- JSON


def test_json_report_matches_the_documented_top_level_schema() -> None:
    result = review_diff(make_added_file_diff("app/m.py", MUTABLE_DEFAULT))
    payload = json.loads(render_json(result))
    assert payload["schema_version"] == "1.0"
    for key in schema_summary()["top_level_keys"]:
        assert key in payload, key
    assert set(payload["engine"]) == {"name", "version", "mode"}
    assert set(payload["summary"]) == {
        "total_findings",
        "by_severity",
        "by_category",
        "deterministic",
        "heuristic",
    }
    for key in schema_summary()["finding_keys"]:
        assert key in payload["findings"][0], key


def test_json_report_is_byte_identical_across_runs() -> None:
    diff = make_added_file_diff("app/m.py", MUTABLE_DEFAULT)
    first = render_json(review_diff(diff))
    second = render_json(review_diff(diff))
    assert first == second


def test_json_report_has_no_timestamp_unless_explicitly_enabled() -> None:
    result = review_diff(make_added_file_diff("app/m.py", MUTABLE_DEFAULT))
    assert "generated_at" not in json.loads(render_json(result))


def test_json_report_can_include_a_timestamp_when_asked() -> None:
    from dataclasses import replace

    result = review_diff(make_added_file_diff("app/m.py", MUTABLE_DEFAULT))
    stamped = replace(result, generated_at="2026-10-17T00:00:00Z")
    payload = json.loads(render_json(stamped))
    assert payload["generated_at"] == "2026-10-17T00:00:00Z"


def test_json_round_trips_and_keeps_confidence_meaning() -> None:
    result = review_diff(make_added_file_diff("app/m.py", MUTABLE_DEFAULT))
    payload = json.loads(render_json(result))
    finding = payload["findings"][0]
    assert finding["confidence_meaning"].strip()
    assert finding["class"] in {"deterministic", "heuristic"}
    assert isinstance(finding["deterministic"], bool)


def test_json_can_omit_confidence_meanings_for_compact_output() -> None:
    result = review_diff(make_added_file_diff("app/m.py", MUTABLE_DEFAULT))
    payload = json.loads(render_json(result, include_confidence_meaning=False))
    assert "confidence_meaning" not in payload["findings"][0]


def test_suppressed_findings_are_visible_in_the_json_report() -> None:
    cfg = PrismConfig(min_severity="critical")
    result = review_diff(make_added_file_diff("app/m.py", MUTABLE_DEFAULT), cfg=cfg)
    assert result.findings == ()
    assert result.suppressed, "suppression must be recorded, not silently dropped"
    payload = json.loads(render_json(result))
    assert payload["summary"]["total_findings"] == 0
    assert payload["suppressed_findings"], "a short report must show what was suppressed"
    assert {item["policy"] for item in payload["suppressed_findings"]} == {"min_severity=critical"}


def test_report_rule_catalogue_lists_every_registered_rule() -> None:
    from prism.analyzers.registry import build_default_registry

    result = review_diff(make_added_file_diff("app/m.py", MUTABLE_DEFAULT))
    catalogue = result.rule_catalog
    assert set(catalogue) == set(build_default_registry().rule_ids())
    for entry in catalogue.values():
        assert entry["class"] in {"deterministic", "heuristic"}


def test_markdown_lists_limitations_and_scoped_skips() -> None:
    diff = make_added_file_diff("app/m.py", MUTABLE_DEFAULT) + (
        "diff --git a/assets/logo.png b/assets/logo.png\n"
        "index 1111111..2222222 100644\n"
        "Binary files a/assets/logo.png and b/assets/logo.png differ\n"
    )
    result = review_diff(diff)
    report = render_markdown(result)
    assert "binary_file" in report
    assert "assets/logo.png" in report
    assert "Static analysis only" in report


@pytest.mark.parametrize(
    "value",
    ["", None, 0, ["a", "b"], {"k": "v"}, "x" * 5000],
)
def test_report_rendering_survives_odd_metadata_values(value: object) -> None:
    from dataclasses import replace

    result = review_diff(make_added_file_diff("app/m.py", MUTABLE_DEFAULT))
    report = render_markdown(replace(result, metadata={"odd": value}))
    assert "# PRISM review report" in report
