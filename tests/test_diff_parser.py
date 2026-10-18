"""Diff parsing, changed-line mapping, malformed input and limit behaviour."""

from __future__ import annotations

import pytest

from prism.core.config import PrismConfig
from prism.core.exceptions import (
    InputTooLargeError,
    InputValidationError,
    TooManyFilesError,
    UnsupportedInputError,
)
from prism.core.limits import LimitPolicy, check_diff_size, check_file_count
from prism.core.types import FileStatus
from prism.diff.mapping import (
    build_added_line_fragment,
    changed_line_numbers,
    is_complete_new_file,
    reconstruct_new_side,
)
from prism.diff.parser import parse_unified_diff
from tests.conftest import make_added_file_diff, make_modified_file_diff

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def test_added_file_is_parsed_with_new_side_line_numbers() -> None:
    parsed = parse_unified_diff(make_added_file_diff("app/new.py", "a = 1\nb = 2\n"))
    assert len(parsed.files) == 1
    file = parsed.files[0]
    assert file.status is FileStatus.ADDED
    assert file.path == "app/new.py"
    assert file.old_path is None
    assert file.analyzable
    assert [line.new_lineno for line in file.added_lines] == [1, 2]
    assert changed_line_numbers(file) == {1, 2}


def test_modified_file_maps_lines_across_multiple_hunks() -> None:
    diff = (
        "diff --git a/pkg/mod.py b/pkg/mod.py\n"
        "--- a/pkg/mod.py\n"
        "+++ b/pkg/mod.py\n"
        "@@ -1,3 +1,4 @@ def alpha():\n"
        " import os\n"
        "+import sys\n"
        " import re\n"
        " import json\n"
        "@@ -20,3 +21,4 @@ def beta():\n"
        " x = 1\n"
        "+y = 2\n"
        " z = 3\n"
        " w = 4\n"
    )
    parsed = parse_unified_diff(diff)
    file = parsed.files[0]
    assert file.status is FileStatus.MODIFIED
    assert [line.new_lineno for line in file.added_lines] == [2, 22]
    assert file.hunks[0].section == "def alpha():"
    assert file.hunks[1].section == "def beta():"


def test_deleted_file_is_recorded_and_not_analyzable() -> None:
    diff = (
        "diff --git a/old.py b/old.py\n"
        "deleted file mode 100644\n"
        "--- a/old.py\n"
        "+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n"
        "-a = 1\n"
        "-b = 2\n"
    )
    parsed = parse_unified_diff(diff)
    file = parsed.files[0]
    assert file.status is FileStatus.DELETED
    assert file.new_path is None
    assert file.path == "old.py"
    assert not file.analyzable
    assert any(record.reason == "deleted_file" for record in parsed.skipped)


def test_rename_is_parsed_with_both_paths() -> None:
    diff = (
        "diff --git a/legacy/name.py b/app/name.py\n"
        "similarity index 95%\n"
        "rename from legacy/name.py\n"
        "rename to app/name.py\n"
        "--- a/legacy/name.py\n"
        "+++ b/app/name.py\n"
        "@@ -1,2 +1,3 @@\n"
        " a = 1\n"
        "+b = 2\n"
        " c = 3\n"
    )
    parsed = parse_unified_diff(diff)
    file = parsed.files[0]
    assert file.status is FileStatus.RENAMED
    assert file.old_path == "legacy/name.py"
    assert file.new_path == "app/name.py"
    assert file.path == "app/name.py"
    assert file.previous_path == "legacy/name.py"


def test_binary_file_is_skipped_with_a_reason_not_an_error() -> None:
    diff = (
        "diff --git a/assets/logo.png b/assets/logo.png\n"
        "index 1111111..2222222 100644\n"
        "Binary files a/assets/logo.png and b/assets/logo.png differ\n"
    )
    parsed = parse_unified_diff(diff)
    assert parsed.files[0].status is FileStatus.BINARY
    assert not parsed.files[0].analyzable
    reasons = [record.reason for record in parsed.skipped]
    assert "binary_file" in reasons
    assert parsed.diagnostics == ()  # expected, not a failure


def test_file_without_a_patch_is_recorded_as_skipped() -> None:
    diff = "diff --git a/big.py b/big.py\nindex aaa..bbb 100644\n--- a/big.py\n+++ b/big.py\n"
    parsed = parse_unified_diff(diff)
    assert not parsed.files[0].patch_available
    assert any(record.reason == "no_patch_available" for record in parsed.skipped)


def test_empty_diff_is_rejected() -> None:
    with pytest.raises(InputValidationError):
        parse_unified_diff("   \n\n")


def test_non_diff_input_is_rejected() -> None:
    with pytest.raises(UnsupportedInputError):
        parse_unified_diff("this is just prose, not a diff at all\n")


def test_combined_merge_diff_is_rejected_with_guidance() -> None:
    with pytest.raises(UnsupportedInputError) as excinfo:
        parse_unified_diff("diff --cc file.py\nindex aaa,bbb..ccc\n")
    assert "two-way diff" in str(excinfo.value.details["hint"])


def test_truncated_hunk_declares_a_mismatch_and_keeps_going() -> None:
    diff = "diff --git a/t.py b/t.py\n--- a/t.py\n+++ b/t.py\n@@ -1,10 +1,10 @@\n a = 1\n+b = 2\n"
    parsed = parse_unified_diff(diff)
    assert any("line numbers in this hunk may be unreliable" in d for d in parsed.diagnostics)
    # The added line is still usable, and the parser did not raise.
    assert [line.new_lineno for line in parsed.files[0].added_lines] == [2]


def test_unparseable_hunk_header_is_flagged_not_fatal() -> None:
    diff = "diff --git a/t.py b/t.py\n--- a/t.py\n+++ b/t.py\n@@ this is not a header @@\n+x = 1\n"
    parsed = parse_unified_diff(diff)
    assert parsed.files[0].hunks
    assert parsed.files[0].hunks[0].malformed
    assert any("unparseable hunk header" in d for d in parsed.diagnostics)


def test_crlf_line_endings_do_not_corrupt_content() -> None:
    diff = (
        "diff --git a/w.py b/w.py\r\n"
        "--- a/w.py\r\n"
        "+++ b/w.py\r\n"
        "@@ -1,1 +1,2 @@\r\n"
        " a = 1\r\n"
        "+b = 2\r\n"
    )
    parsed = parse_unified_diff(diff)
    assert [line.content for line in parsed.files[0].added_lines] == ["b = 2"]
    assert "\r" not in parsed.files[0].added_lines[0].content


def test_no_newline_marker_is_recorded() -> None:
    diff = (
        "diff --git a/n.py b/n.py\n"
        "--- a/n.py\n"
        "+++ b/n.py\n"
        "@@ -1 +1 @@\n"
        "-a = 1\n"
        "+a = 2\n"
        "\\ No newline at end of file\n"
    )
    parsed = parse_unified_diff(diff)
    assert parsed.files[0].added_lines[0].no_newline_at_eof


def test_paths_with_spaces_and_quotes_are_handled() -> None:
    diff = (
        'diff --git "a/dir with space/f.py" "b/dir with space/f.py"\n'
        '--- "a/dir with space/f.py"\n'
        '+++ "b/dir with space/f.py"\n'
        "@@ -1,1 +1,2 @@\n"
        " a = 1\n"
        "+b = 2\n"
    )
    parsed = parse_unified_diff(diff)
    assert parsed.files[0].path == "dir with space/f.py"


def test_a_removed_line_starting_with_dashes_is_not_mistaken_for_a_header() -> None:
    """Regression: '--- x' as hunk content was skipped as if it were a file header."""
    diff = (
        "diff --git a/d.py b/d.py\n"
        "--- a/d.py\n"
        "+++ b/d.py\n"
        "@@ -1,3 +1,2 @@\n"
        "--- removed separator line\n"
        "-# real removed comment\n"
        " kept = 1\n"
    )
    parsed = parse_unified_diff(diff)
    removed = [line.content for line in parsed.files[0].removed_lines]
    assert "-- removed separator line" in removed
    assert "# real removed comment" in removed


def test_nul_bytes_and_control_characters_do_not_crash_the_parser() -> None:
    diff = (
        "diff --git a/c.py b/c.py\n"
        "--- a/c.py\n"
        "+++ b/c.py\n"
        "@@ -1,1 +1,2 @@\n"
        " a = 1\n"
        "+b = '\x00\x01\x02'\n"
    )
    parsed = parse_unified_diff(diff)
    assert parsed.files[0].added_lines


def test_very_long_single_line_is_processed() -> None:
    long_line = "x" * 200_000
    diff = make_added_file_diff("huge.py", long_line)
    parsed = parse_unified_diff(diff)
    assert len(parsed.files[0].added_lines[0].content) == 200_000


def test_oversized_diff_raises_with_the_limit_in_the_details() -> None:
    with pytest.raises(InputValidationError) as excinfo:
        parse_unified_diff(make_added_file_diff("a.py", "x = 1\n"), max_bytes=10)
    assert excinfo.value.details["limit"] == 10
    assert excinfo.value.details["observed"] > 10


def test_file_count_limit_truncates_and_records_it() -> None:
    diff = "".join(make_added_file_diff(f"f{i}.py", "a = 1\n") for i in range(5))
    parsed = parse_unified_diff(diff, max_files=2)
    assert len(parsed.files) == 2
    assert parsed.truncated
    assert any(record.reason == "file_limit_reached" for record in parsed.skipped)


def test_oversized_patch_is_skipped_rather_than_partially_analysed() -> None:
    diff = make_added_file_diff("big.py", "a = 1\n" * 100)
    parsed = parse_unified_diff(diff, max_patch_bytes=50)
    assert not parsed.files[0].patch_available
    assert any(record.reason == "patch_too_large" for record in parsed.skipped)


def test_limit_helpers_raise_typed_errors() -> None:
    policy = LimitPolicy(max_diff_bytes=10, max_files=1)
    assert check_diff_size(5, policy).exceeded is False
    with pytest.raises(InputTooLargeError):
        check_diff_size(11, policy)
    assert check_file_count(1, policy).exceeded is False
    with pytest.raises(TooManyFilesError):
        check_file_count(2, policy)


def test_only_a_complete_added_file_yields_a_full_source() -> None:
    added = parse_unified_diff(make_added_file_diff("ok.py", "a = 1\nb = 2\n")).files[0]
    assert is_complete_new_file(added)
    assert reconstruct_new_side(added) == "a = 1\nb = 2\n"

    modified = parse_unified_diff(make_modified_file_diff("mod.py", ["y = 2"])).files[0]
    assert not is_complete_new_file(modified)
    assert reconstruct_new_side(modified) is None


def test_added_line_fragment_is_dedented_and_keeps_the_line_map() -> None:
    diff = (
        "diff --git a/frag.py b/frag.py\n"
        "--- a/frag.py\n"
        "+++ b/frag.py\n"
        "@@ -10,1 +10,3 @@ def f():\n"
        "     pre = 1\n"
        "+    if pre:\n"
        "+        raise ValueError('x')\n"
    )
    file = parse_unified_diff(diff).files[0]
    fragment = build_added_line_fragment(file)
    assert fragment is not None
    text, line_map = fragment
    assert text == "if pre:\n    raise ValueError('x')\n"
    assert line_map == (11, 12)


def test_added_line_fragment_is_none_when_the_diff_only_removes_lines() -> None:
    diff = (
        "diff --git a/onlydel.py b/onlydel.py\n"
        "--- a/onlydel.py\n"
        "+++ b/onlydel.py\n"
        "@@ -1,2 +1,1 @@\n"
        "-gone = 1\n"
        " kept = 2\n"
    )
    file = parse_unified_diff(diff).files[0]
    assert build_added_line_fragment(file) is None


def test_config_limit_policy_reflects_configuration() -> None:
    cfg = PrismConfig(max_diff_bytes=123, max_files=7)
    assert cfg.limit_policy.max_diff_bytes == 123
    assert cfg.limit_policy.max_files == 7
