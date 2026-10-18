"""Unified-diff parsing.

Design constraints taken from the requirement text:

* Every file entry may or may not carry a usable patch. A missing or binary patch is a
  recorded ``skipped`` reason, never a crash and never an assumption.
* Line numbers are taken from the hunk headers of the new side; the parser never guesses.
* Malformed or truncated input degrades into a diagnostic on the offending file instead of
  aborting the whole review, unless the input is not a diff at all.
* Untrusted content is treated purely as text. Nothing here is imported, evaluated or
  executed.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404 - fixed argv lists, shell disabled, no diff content passed
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from prism.core.exceptions import InputValidationError, UnsupportedInputError
from prism.core.types import FileStatus

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")

_CRLF = "\r\n"


@dataclass(frozen=True)
class DiffLine:
    """One line of a hunk with both side line numbers where known."""

    kind: str  # "context" | "add" | "del"
    content: str
    old_lineno: int | None = None
    new_lineno: int | None = None
    no_newline_at_eof: bool = False

    @property
    def is_added(self) -> bool:
        return self.kind == "add"

    @property
    def is_removed(self) -> bool:
        return self.kind == "del"


@dataclass(frozen=True)
class Hunk:
    """A single ``@@`` hunk."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    section: str
    lines: tuple[DiffLine, ...]
    malformed: bool = False
    malformed_reason: str | None = None

    @property
    def added_lines(self) -> tuple[DiffLine, ...]:
        return tuple(line for line in self.lines if line.is_added)

    @property
    def removed_lines(self) -> tuple[DiffLine, ...]:
        return tuple(line for line in self.lines if line.is_removed)


@dataclass(frozen=True)
class SkipRecord:
    """A file or region PRISM deliberately did not analyse, with the exact reason."""

    path: str | None
    reason: str
    detail: str | None = None

    def describe(self) -> str:
        if self.detail:
            return f"{self.path or '<unknown>'}: {self.reason} ({self.detail})"
        return f"{self.path or '<unknown>'}: {self.reason}"


@dataclass(frozen=True)
class FileDiff:
    """One file entry of a diff."""

    old_path: str | None
    new_path: str | None
    status: FileStatus
    hunks: tuple[Hunk, ...] = ()
    is_binary: bool = False
    patch_available: bool = True
    old_mode: str | None = None
    new_mode: str | None = None
    previous_path: str | None = None
    diagnostics: tuple[str, ...] = ()

    @property
    def path(self) -> str:
        """The path findings should be anchored to (new side when it exists)."""
        return self.new_path or self.old_path or "<unknown>"

    @property
    def old_side_path(self) -> str | None:
        return self.old_path

    @property
    def extension(self) -> str:
        name = self.path
        dot = name.rfind(".")
        return name[dot:].lower() if dot > 0 else ""

    @property
    def added_lines(self) -> tuple[DiffLine, ...]:
        return tuple(line for hunk in self.hunks for line in hunk.added_lines)

    @property
    def removed_lines(self) -> tuple[DiffLine, ...]:
        return tuple(line for hunk in self.hunks for line in hunk.removed_lines)

    @property
    def analyzable(self) -> bool:
        """Whether the file has content worth analysing."""
        return (
            self.patch_available
            and not self.is_binary
            and self.status is not FileStatus.DELETED
            and bool(self.hunks)
        )

    def added_line_numbers(self) -> tuple[int, ...]:
        return tuple(line.new_lineno for line in self.added_lines if line.new_lineno is not None)

    def with_diagnostic(self, message: str) -> FileDiff:
        return replace(self, diagnostics=(*self.diagnostics, message))


@dataclass(frozen=True)
class ParsedDiff:
    """A whole diff plus its scope bookkeeping."""

    files: tuple[FileDiff, ...] = ()
    skipped: tuple[SkipRecord, ...] = ()
    diagnostics: tuple[str, ...] = ()
    source: str = "unified"
    truncated: bool = False

    @property
    def total_added_lines(self) -> int:
        return sum(len(f.added_lines) for f in self.files)

    @property
    def total_removed_lines(self) -> int:
        return sum(len(f.removed_lines) for f in self.files)

    def by_path(self, path: str) -> FileDiff | None:
        for file in self.files:
            if file.path == path or file.new_path == path or file.old_path == path:
                return file
        return None


# --------------------------------------------------------------------- helpers


def _unquote_git_path(raw: str) -> str:
    """Decode a git-quoted path (``"a/p\\303\\251.py"``) into plain text."""
    text = raw.strip()
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        body = text[1:-1]
        try:
            return body.encode("latin-1", "backslashreplace").decode("unicode_escape")
        except (UnicodeDecodeError, UnicodeEncodeError):
            return body
    return text


def _strip_prefix(raw: str, *, prefixes: Sequence[str] = ("a/", "b/")) -> str:
    """Remove a single git path prefix, preserving the rest of the path."""
    text = _unquote_git_path(raw)
    if text == "/dev/null":
        return text
    for prefix in prefixes:
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


def _is_no_newline_marker(line: str) -> bool:
    return line.startswith("\\")


def _looks_like_diff(text: str) -> bool:
    for line in text.splitlines():
        if line.startswith("diff --git ") or line.startswith("--- ") or line.startswith("@@"):
            return True
        if line.strip():
            return False
    return False


# --------------------------------------------------------------------- parser


def parse_unified_diff(
    text: str,
    *,
    max_bytes: int | None = None,
    max_files: int | None = None,
    max_patch_bytes: int | None = None,
    source: str = "unified",
) -> ParsedDiff:
    """Parse a unified diff into :class:`ParsedDiff`.

    ``max_bytes`` is enforced in UTF-8 bytes. ``max_patch_bytes`` marks oversized single
    patches as skipped instead of analysing a partial picture.
    """
    if text is None or text.strip() == "":
        raise InputValidationError("Diff is empty; nothing to review.")

    encoded_size = len(text.encode("utf-8", errors="replace"))
    if max_bytes is not None and encoded_size > max_bytes:
        raise InputValidationError(
            "Diff exceeds the configured size limit.",
            details={"limit": max_bytes, "observed": encoded_size, "unit": "bytes"},
        )

    # Combined and merge diffs must be detected before the generic shape check, because
    # 'diff --cc' does not match any of the single-file markers.
    if text.lstrip().startswith(("diff --cc ", "diff --combined ")):
        raise UnsupportedInputError(
            "Combined (merge) diffs are not supported.",
            details={"hint": "Generate a two-way diff, for example 'git diff commit1 commit2'."},
        )

    if not _looks_like_diff(text):
        raise UnsupportedInputError(
            "Input does not look like a unified diff.",
            details={"hint": "Expected 'diff --git', '---' or '@@' markers."},
        )

    lines = text.split(_CRLF) if _CRLF in text else text.split("\n")
    files: list[FileDiff] = []
    skipped: list[SkipRecord] = []
    diagnostics: list[str] = []
    truncated = False

    index = 0
    total = len(lines)

    while index < total:
        line = lines[index]
        if not line.startswith("diff --git "):
            index += 1
            continue

        header = line
        index += 1
        meta: dict[str, str] = {}
        binary = False
        body: list[str] = []

        # Collect the file section: everything until the next 'diff --git'.
        while index < total and not lines[index].startswith("diff --git "):
            current = lines[index]
            if current.startswith("new file mode"):
                meta["new_file"] = "1"
            elif current.startswith("deleted file mode"):
                meta["deleted_file"] = "1"
            elif current.startswith("old mode"):
                meta["old_mode"] = current.partition(" ")[2].strip()
            elif current.startswith("new mode"):
                meta["new_mode"] = current.partition(" ")[2].strip()
            elif current.startswith("rename from "):
                meta["rename_from"] = current[len("rename from ") :].strip()
            elif current.startswith("rename to "):
                meta["rename_to"] = current[len("rename to ") :].strip()
            elif current.startswith("copy from "):
                meta["copy_from"] = current[len("copy from ") :].strip()
            elif current.startswith("copy to "):
                meta["copy_to"] = current[len("copy to ") :].strip()
            elif current.startswith("Binary files ") or current.startswith("GIT binary patch"):
                binary = True
            elif current.startswith("--- "):
                meta["old_raw"] = current[4:].strip()
            elif current.startswith("+++ "):
                meta["new_raw"] = current[4:].strip()
            body.append(current)
            index += 1

        file_diff = _build_file(
            header=header,
            meta=meta,
            body=body,
            binary=binary,
            max_patch_bytes=max_patch_bytes,
            skipped=skipped,
            diagnostics=diagnostics,
        )
        if file_diff is not None:
            files.append(file_diff)

        if max_files is not None and len(files) > max_files:
            truncated = True
            diagnostics.append(
                f"File limit of {max_files} reached; remaining files were not parsed."
            )
            files = files[:max_files]
            skipped.append(
                SkipRecord(
                    path=None,
                    reason="file_limit_reached",
                    detail=f"only the first {max_files} files were parsed",
                )
            )
            break

    if not files:
        diagnostics.append("No file entries were found in the diff.")

    return ParsedDiff(
        files=tuple(files),
        skipped=tuple(skipped),
        diagnostics=tuple(diagnostics),
        source=source,
        truncated=truncated,
    )


def _build_file(
    *,
    header: str,
    meta: dict[str, str],
    body: list[str],
    binary: bool,
    max_patch_bytes: int | None,
    skipped: list[SkipRecord],
    diagnostics: list[str],
) -> FileDiff | None:
    old_raw = meta.get("old_raw")
    new_raw = meta.get("new_raw")

    # Paths from the 'diff --git' header are a fallback when ---/+++ are absent.
    header_old: str | None = None
    header_new: str | None = None
    header_parts = _split_git_header(header)
    if header_parts:
        header_old, header_new = header_parts

    old_path = _strip_prefix(old_raw) if old_raw else header_old
    new_path = _strip_prefix(new_raw) if new_raw else header_new
    if old_path == "/dev/null":
        old_path = None
    if new_path == "/dev/null":
        new_path = None

    if "rename_from" in meta:
        old_path = meta["rename_from"]
        new_path = meta.get("rename_to", new_path)
    if "copy_from" in meta:
        old_path = meta["copy_from"]
        new_path = meta.get("copy_to", new_path)

    if "new_file" in meta:
        status = FileStatus.ADDED
    elif "deleted_file" in meta:
        status = FileStatus.DELETED
    elif (
        "rename_from" in meta
        or "copy_from" in meta
        or (header_old and header_new and header_old != header_new)
    ):
        status = FileStatus.RENAMED
    else:
        status = FileStatus.MODIFIED

    path = new_path or old_path
    if path is None:
        skipped.append(SkipRecord(path=None, reason="unresolvable_path", detail=header))
        return None

    if binary:
        skipped.append(
            SkipRecord(path=path, reason="binary_file", detail="no textual patch available")
        )
        return FileDiff(
            old_path=old_path,
            new_path=new_path,
            status=FileStatus.BINARY,
            is_binary=True,
            patch_available=False,
            old_mode=meta.get("old_mode"),
            new_mode=meta.get("new_mode"),
            previous_path=meta.get("rename_from"),
        )

    patch_bytes = sum(len(line.encode("utf-8", errors="replace")) + 1 for line in body)
    if max_patch_bytes is not None and patch_bytes > max_patch_bytes:
        skipped.append(
            SkipRecord(
                path=path,
                reason="patch_too_large",
                detail=f"{patch_bytes} bytes exceeds limit {max_patch_bytes}",
            )
        )
        return FileDiff(
            old_path=old_path,
            new_path=new_path,
            status=status,
            patch_available=False,
            old_mode=meta.get("old_mode"),
            new_mode=meta.get("new_mode"),
            previous_path=meta.get("rename_from"),
        )

    hunks, file_diags = _parse_hunks(body)
    if not hunks and status is not FileStatus.DELETED:
        skipped.append(
            SkipRecord(
                path=path,
                reason="no_patch_available",
                detail="file entry contains no '@@' hunks",
            )
        )
        return FileDiff(
            old_path=old_path,
            new_path=new_path,
            status=status,
            patch_available=False,
            old_mode=meta.get("old_mode"),
            new_mode=meta.get("new_mode"),
            previous_path=meta.get("rename_from"),
            diagnostics=tuple(file_diags),
        )

    if status is FileStatus.DELETED:
        skipped.append(
            SkipRecord(
                path=path,
                reason="deleted_file",
                detail="only removals are present; nothing to analyse as new code",
            )
        )

    diagnostics.extend(f"{path}: {message}" for message in file_diags)
    return FileDiff(
        old_path=old_path,
        new_path=new_path,
        status=status,
        hunks=tuple(hunks),
        old_mode=meta.get("old_mode"),
        new_mode=meta.get("new_mode"),
        previous_path=meta.get("rename_from"),
        diagnostics=tuple(file_diags),
    )


def _split_git_header(header: str) -> tuple[str, str] | None:
    """Parse ``diff --git a/x b/y`` including quoted paths with spaces."""
    rest = header[len("diff --git ") :].strip()
    if not rest:
        return None
    if rest.startswith('"'):
        # quoted form: "a/x y" "b/x y"
        parts = re.findall(r'"(?:[^"\\]|\\.)*"', rest)
        if len(parts) == 2:
            return _strip_prefix(parts[0]), _strip_prefix(parts[1])
        return None
    if rest.count(" ") == 1:
        left, right = rest.split(" ")
        return _strip_prefix(left), _strip_prefix(right)
    # unquoted path containing spaces: split on the ' b/' boundary
    marker = rest.find(" b/")
    if marker > 0:
        return _strip_prefix(rest[:marker]), _strip_prefix(rest[marker + 1 :])
    return None


def _parse_hunks(body: Iterable[str]) -> tuple[list[Hunk], list[str]]:
    hunks: list[Hunk] = []
    diagnostics: list[str] = []
    current_header: tuple[int, int, int, int, str] | None = None
    current_lines: list[DiffLine] = []
    old_lineno = new_lineno = 0
    old_remaining = new_remaining = 0
    malformed = False
    malformed_reason: str | None = None

    def flush() -> None:
        nonlocal current_header, current_lines, malformed, malformed_reason
        if current_header is None:
            return
        old_start, old_count, new_start, new_count, section = current_header
        hunks.append(
            Hunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                section=section,
                lines=tuple(current_lines),
                malformed=malformed,
                malformed_reason=malformed_reason,
            )
        )
        if malformed and malformed_reason:
            diagnostics.append(f"hunk at new line {new_start} is malformed: {malformed_reason}")
        current_header = None
        current_lines = []
        malformed = False
        malformed_reason = None

    for raw in body:
        if raw.startswith("@@ "):
            flush()
            match = _HUNK_RE.match(raw)
            if not match:
                malformed = True
                malformed_reason = "unparseable hunk header"
                current_header = (0, 0, 0, 0, "")
                continue
            old_start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) is not None else 1
            new_start = int(match.group(3))
            new_count = int(match.group(4)) if match.group(4) is not None else 1
            current_header = (old_start, old_count, new_start, new_count, match.group(5).strip())
            old_lineno, new_lineno = old_start, new_start
            old_remaining, new_remaining = old_count, new_count
            continue

        if current_header is None:
            continue

        if _is_no_newline_marker(raw):
            if current_lines:
                last = current_lines.pop()
                current_lines.append(replace(last, no_newline_at_eof=True))
            continue

        if raw == "":
            # An empty line outside a hunk is a separator; inside a hunk it is a context
            # line whose leading space was stripped by a lossy transport.
            if old_remaining > 0 or new_remaining > 0:
                current_lines.append(
                    DiffLine(
                        kind="context",
                        content="",
                        old_lineno=old_lineno,
                        new_lineno=new_lineno,
                    )
                )
                old_lineno += 1
                new_lineno += 1
                old_remaining -= 1
                new_remaining -= 1
            continue

        marker, content = raw[0], raw[1:]
        if marker == "+":
            current_lines.append(DiffLine(kind="add", content=content, new_lineno=new_lineno))
            new_lineno += 1
            new_remaining -= 1
        elif marker == "-":
            current_lines.append(DiffLine(kind="del", content=content, old_lineno=old_lineno))
            old_lineno += 1
            old_remaining -= 1
        elif marker == " ":
            current_lines.append(
                DiffLine(
                    kind="context",
                    content=content,
                    old_lineno=old_lineno,
                    new_lineno=new_lineno,
                )
            )
            old_lineno += 1
            new_lineno += 1
            old_remaining -= 1
            new_remaining -= 1
        elif marker == "\\":
            continue
        else:
            malformed = True
            if malformed_reason is None:
                malformed_reason = f"unexpected line prefix {marker!r} inside hunk"

    flush()

    # Consistency check: the hunk counters must agree with the header counts.
    for hunk in hunks:
        actual_old = sum(1 for line in hunk.lines if line.kind in {"context", "del"})
        actual_new = sum(1 for line in hunk.lines if line.kind in {"context", "add"})
        if hunk.malformed:
            continue
        if actual_old != hunk.old_count or actual_new != hunk.new_count:
            diagnostics.append(
                "hunk at new line "
                f"{hunk.new_start} declares {hunk.old_count}/{hunk.new_count} lines "
                f"but contains {actual_old}/{actual_new}; line numbers in this hunk may be "
                "unreliable"
            )

    return hunks, diagnostics


def parse_local_git_diff(
    repo_path: str,
    *,
    base: str | None = None,
    head: str | None = None,
    max_bytes: int | None = None,
    timeout_seconds: float = 60.0,
) -> ParsedDiff:
    """Generate a diff from a local Git repository and parse it.

    Git is invoked with an argument list (never a shell) and a timeout. No repository code
    is executed or imported; only ``git diff`` output is read.
    """
    args = ["git", "-C", repo_path, "diff", "--no-color", "--no-ext-diff", "--unified=3"]
    if base and head:
        args.append(f"{base}..{head}")
    elif base:
        args.append(base)

    try:
        completed = subprocess.run(  # noqa: S603  # nosec B603 - fixed argv, no shell
            args,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise InputValidationError(
            "Git executable not found while generating a local diff.",
            details={"hint": "Install Git or supply a diff file instead."},
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise InputValidationError(
            "Git diff timed out.",
            details={"timeout_seconds": timeout_seconds},
        ) from exc

    if completed.returncode != 0:
        raise InputValidationError(
            "Git could not produce a diff for this repository.",
            details={
                "exit_code": completed.returncode,
                "stderr_tail": (completed.stderr or "").strip().splitlines()[-3:],
            },
        )

    if not (completed.stdout or "").strip():
        raise InputValidationError(
            "Git reported no changes; there is no diff to review.",
            details={"hint": "Commit or stage changes, or compare two revisions with --base."},
        )

    return parse_unified_diff(
        completed.stdout,
        max_bytes=max_bytes,
        source="local_git",
    )
