"""Turn the GitHub files listing into parsed, analysable diffs.

The REST ``files`` endpoint returns one ``patch`` per file, and that patch is exactly what
PRISM analyses. This module rebuilds a unified-diff-shaped structure from those patches so
the same engine handles the local-diff and the pull-request modes.

Two honest cases are handled explicitly:

* **No patch at all.** GitHub omits ``patch`` for binary files and for very large diffs. Such
  an entry becomes a skipped record with the API's own ``status``; PRISM does not invent a
  patch and does not silently analyse nothing.
* **Deleted files.** They are recorded as deleted and their removals are not treated as new
  code.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from prism.core.exceptions import InputValidationError
from prism.core.types import FileStatus
from prism.diff.parser import FileDiff, ParsedDiff, SkipRecord, parse_unified_diff
from prism.github.client import GitHubFileEntry

_STATUS_MAP = {
    "added": FileStatus.ADDED,
    "modified": FileStatus.MODIFIED,
    "removed": FileStatus.DELETED,
    "deleted": FileStatus.DELETED,
    "renamed": FileStatus.RENAMED,
    "changed": FileStatus.MODIFIED,
    "copied": FileStatus.RENAMED,
}


def _synthetic_diff_for_entry(entry: GitHubFileEntry) -> str:
    """Wrap a single-file patch in the minimal unified-diff envelope.

    The patch from the API starts at the first ``@@``; the parser needs the path headers, so
    they are reconstructed from the entry's own fields.
    """
    old_path = entry.previous_filename or entry.filename
    new_path = entry.filename
    status = _STATUS_MAP.get(entry.status, FileStatus.MODIFIED)

    header = [f"diff --git a/{old_path} b/{new_path}"]
    if status is FileStatus.ADDED:
        header.append("new file mode 100644")
    elif status is FileStatus.DELETED:
        header.append("deleted file mode 100644")
    elif status is FileStatus.RENAMED:
        header.append(f"rename from {old_path}")
        header.append(f"rename to {new_path}")
    old_marker = "/dev/null" if status is FileStatus.ADDED else f"a/{old_path}"
    new_marker = "/dev/null" if status is FileStatus.DELETED else f"b/{new_path}"
    header.append(f"--- {old_marker}")
    header.append(f"+++ {new_marker}")
    body = "\n".join((entry.patch or "").splitlines())
    return "\n".join(header) + "\n" + body + "\n"


def files_from_github(
    entries: Sequence[GitHubFileEntry],
    *,
    max_files: int | None = None,
    max_patch_bytes: int | None = None,
    additional_notes: Iterable[Mapping[str, Any]] = (),
) -> ParsedDiff:
    """Build a :class:`ParsedDiff` from GitHub file entries."""
    files: list[FileDiff] = []
    skipped: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    truncated = False

    for note in additional_notes:
        skipped.append(dict(note))

    for index, entry in enumerate(entries):
        if max_files is not None and index >= max_files:
            truncated = True
            skipped.append(
                {
                    "path": entry.filename or None,
                    "reason": "file_limit_reached",
                    "detail": f"only the first {max_files} entries were analysed",
                }
            )
            break

        status = _STATUS_MAP.get(entry.status, FileStatus.UNKNOWN)
        if not entry.has_patch:
            skipped.append(
                {
                    "path": entry.filename or None,
                    "reason": (
                        "binary_file" if status is FileStatus.BINARY else "no_patch_available"
                    ),
                    "detail": (
                        "the API returned no patch for this file; GitHub omits patches for "
                        "binary files and for very large diffs"
                    ),
                }
            )
            files.append(
                FileDiff(
                    old_path=entry.previous_filename or entry.filename or None,
                    new_path=entry.filename or None,
                    status=FileStatus.BINARY if "binary" in entry.status.lower() else status,
                    is_binary="binary" in entry.status.lower(),
                    patch_available=False,
                    previous_path=entry.previous_filename,
                )
            )
            continue

        if max_patch_bytes is not None:
            size = len((entry.patch or "").encode("utf-8", errors="replace"))
            if size > max_patch_bytes:
                skipped.append(
                    {
                        "path": entry.filename,
                        "reason": "patch_too_large",
                        "detail": f"{size} bytes exceeds limit {max_patch_bytes}",
                    }
                )
                files.append(
                    FileDiff(
                        old_path=entry.previous_filename or entry.filename or None,
                        new_path=entry.filename or None,
                        status=status,
                        patch_available=False,
                        previous_path=entry.previous_filename,
                    )
                )
                continue

        try:
            single = parse_unified_diff(
                _synthetic_diff_for_entry(entry),
                source="github",
            )
        except InputValidationError as exc:
            diagnostics.append(
                f"{entry.filename}: patch could not be parsed ({exc.code}); the file was "
                "not analysed"
            )
            skipped.append(
                {
                    "path": entry.filename,
                    "reason": "unparsable_patch",
                    "detail": exc.code,
                }
            )
            continue

        for file in single.files:
            files.append(file)
        diagnostics.extend(single.diagnostics)
        skipped.extend(dict(item) for item in _as_dicts(single.skipped))
        if status is FileStatus.DELETED:
            skipped.append(
                {
                    "path": entry.filename,
                    "reason": "deleted_file",
                    "detail": "the file is removed by this pull request",
                }
            )

    return ParsedDiff(
        files=tuple(files),
        skipped=tuple(_dedupe_skips(skipped)),
        diagnostics=tuple(diagnostics),
        source="github",
        truncated=truncated,
    )


def _as_dicts(records: Iterable[SkipRecord]) -> list[dict[str, Any]]:
    return [
        {"path": record.path, "reason": record.reason, "detail": record.detail}
        for record in records
    ]


def _dedupe_skips(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = (
            str(item.get("path") or ""),
            str(item.get("reason") or ""),
            str(item.get("detail") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "path": item.get("path"),
                "reason": item.get("reason"),
                "detail": item.get("detail"),
            }
        )
    return result


__all__ = ["files_from_github"]
