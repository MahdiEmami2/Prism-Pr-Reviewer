"""Changed-line mapping helpers.

These functions answer the only two questions the analysers need about a diff:

1. Which new-side line numbers changed? (for anchoring findings)
2. Can the whole new-side file be reconstructed from this diff?

The second question matters because a partial patch cannot be parsed as Python. When the
answer is "no", AST rules are skipped for that file and the reason is recorded as a scope
diagnostic - PRISM never pretends to have analysed a file it only partly sees.
"""

from __future__ import annotations

from prism.core.types import FileStatus
from prism.diff.parser import FileDiff, Hunk


def added_text(file: FileDiff) -> str:
    """Concatenated added-line text (used for cheap pre-filters)."""
    return "\n".join(line.content for line in file.added_lines)


def changed_line_numbers(file: FileDiff) -> frozenset[int]:
    """New-side line numbers of every added line in the file."""
    return frozenset(line.new_lineno for line in file.added_lines if line.new_lineno is not None)


def line_number_map(file: FileDiff) -> dict[int, str]:
    """Map new-side line number to the added line's content."""
    mapping: dict[int, str] = {}
    for line in file.added_lines:
        if line.new_lineno is not None:
            mapping[line.new_lineno] = line.content
    return mapping


def is_complete_new_file(file: FileDiff) -> bool:
    """True when the patch contains the entire new version of the file.

    This is the case for a freshly added file whose single hunk starts at new line 1 and
    contains exactly the declared number of new-side lines, with no removals. Anything
    else is a partial view.
    """
    if file.status is not FileStatus.ADDED:
        return False
    if len(file.hunks) != 1:
        return False
    hunk = file.hunks[0]
    if hunk.old_count != 0 or hunk.old_start not in {0, 1}:
        return False
    if hunk.new_start != 1:
        return False
    if hunk.removed_lines or hunk.malformed:
        return False
    return len(hunk.added_lines) == hunk.new_count


def reconstruct_new_side(file: FileDiff) -> str | None:
    """Reconstruct the new file content when the patch contains all of it.

    Returns ``None`` when the diff only shows part of the file. Never returns a guess:
    a partially reconstructed file would parse successfully but describe code that does
    not exist, which is worse than reporting the file as not fully analysed.
    """
    if not is_complete_new_file(file):
        return None
    hunk: Hunk = file.hunks[0]
    text = "\n".join(line.content for line in hunk.lines if line.is_added)
    if hunk.lines and hunk.lines[-1].no_newline_at_eof:
        return text
    return text + "\n"


def build_added_line_fragment(file: FileDiff) -> tuple[str, tuple[int | None, ...]] | None:
    """Build a parseable fragment from the added lines of a modified file.

    A unified diff of a modified file does not contain the file's other lines, so the full
    module cannot be reconstructed. Concatenating just the added lines gives a *view* that
    can still be parsed when the added lines form a syntactically self-contained set: the
    fragment is dedented by its minimum indentation so an added block keeps its relative
    structure.

    Returns ``(text, line_map)`` where ``line_map[i]`` is the new-side line number of
    fragment line ``i``, or ``None`` when no usable fragment exists. Findings derived from
    a fragment are labelled as such in the report: a fragment cannot be parsed when the
    change sits in the middle of a block, and a rule that needs surrounding context may be
    missed.
    """
    if is_complete_new_file(file):
        return None
    added = [(line.new_lineno, line.content) for line in file.added_lines]
    if not added:
        return None

    indents = [len(text) - len(text.lstrip(" \t")) for _, text in added if text.strip()]
    if not indents:
        return None
    dedent = min(indents)
    texts: list[str] = []
    line_map: list[int | None] = []
    for new_lineno, text in added:
        stripped = text[dedent:] if text.strip() else ""
        texts.append(stripped)
        line_map.append(new_lineno)
    return "\n".join(texts) + "\n", tuple(line_map)


def hunk_for_line(file: FileDiff, new_lineno: int) -> Hunk | None:
    """Return the hunk containing a new-side line number, if any."""
    for hunk in file.hunks:
        if hunk.new_start <= new_lineno < hunk.new_start + max(hunk.new_count, 1):
            return hunk
    return None


def context_for_line(file: FileDiff, new_lineno: int, radius: int = 2) -> list[str]:
    """Return the diff lines around a new-side line, prefixed with their marker."""
    hunk = hunk_for_line(file, new_lineno)
    if hunk is None:
        return []
    positions = [i for i, line in enumerate(hunk.lines) if line.new_lineno == new_lineno]
    if not positions:
        return []
    center = positions[0]
    window = hunk.lines[max(0, center - radius) : center + radius + 1]
    rendered: list[str] = []
    for line in window:
        marker = {"add": "+", "del": "-", "context": " "}[line.kind]
        rendered.append(f"{marker}{line.content}")
    return rendered
