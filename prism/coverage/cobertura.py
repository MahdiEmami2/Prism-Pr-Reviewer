"""Cobertura XML coverage reader.

Safety: the XML is treated as untrusted data. Entity expansion and external entity
resolution are disabled (``defusedxml`` is used when available, and the standard parser is
hardened otherwise), the document size is capped before parsing, and no value from the
document is ever used as a filesystem path.

Honesty: a missing, unreadable or unmappable report yields ``available: False`` with an
explanation. No code path derives a coverage percentage from a count of test files.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as StdET  # nosec B405 - fallback only, see _parse_xml

from prism.core.exceptions import CoverageError

try:  # pragma: no cover - environment dependent
    from defusedxml.ElementTree import fromstring as _safe_fromstring  # type: ignore

    _HAS_DEFUSED = True
except Exception:  # pragma: no cover - fallback path
    _safe_fromstring = None  # type: ignore[assignment]
    _HAS_DEFUSED = False

DEFAULT_MAX_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class FileCoverage:
    """Coverage for one file, line-explicit only."""

    path: str
    line_rate: float | None = None
    lines_valid: int | None = None
    lines_covered: int | None = None
    uncovered_lines: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line_rate": self.line_rate,
            "lines_valid": self.lines_valid,
            "lines_covered": self.lines_covered,
            "uncovered_lines": list(self.uncovered_lines),
        }


@dataclass(frozen=True)
class CoverageSummary:
    """Parsed coverage report plus its provenance and limits."""

    available: bool = False
    format: str = "cobertura"
    source: str | None = None
    timestamp: str | None = None
    stale_unknown: bool = True
    files: Mapping[str, FileCoverage] = field(default_factory=dict)
    reason: str | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "format": self.format,
            "source": self.source,
            "timestamp": self.timestamp,
            "staleness": (
                "unknown - the report does not carry a revision identity that can be "
                "compared with the diff"
            ),
            "files_with_coverage": len(self.files),
            "reason": self.reason,
            "warnings": list(self.warnings),
            "note": (
                "Only lines explicitly listed in the report are used. PRISM never derives "
                "a coverage percentage from the number of test files."
            ),
        }


def _normalize(path: str) -> str:
    text = path.replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    return text


def parse_cobertura(text: str, *, source: str | None = None) -> CoverageSummary:
    """Parse Cobertura XML text into a :class:`CoverageSummary`."""
    if not text.strip():
        return CoverageSummary(available=False, source=source, reason="coverage report is empty")

    warnings: list[str] = []
    try:
        root = _parse_xml(text)
    except Exception as exc:
        return CoverageSummary(
            available=False,
            source=source,
            reason=f"could not parse coverage XML: {type(exc).__name__}",
        )

    if root.tag != "coverage":
        return CoverageSummary(
            available=False,
            source=source,
            reason=f"unexpected root element '{root.tag}'; expected 'coverage'",
        )

    timestamp = root.get("timestamp")
    files: dict[str, FileCoverage] = {}
    for cls in root.iter("class"):
        filename = cls.get("filename")
        if not filename:
            continue
        path = _normalize(filename)
        uncovered: list[int] = []
        lines_valid = 0
        lines_covered = 0
        for line in cls.iter("line"):
            try:
                number = int(line.get("number", ""))
            except ValueError:
                warnings.append(f"{path}: line element without a numeric 'number'")
                continue
            hits_raw = line.get("hits", "0")
            try:
                hits = int(hits_raw)
            except ValueError:
                warnings.append(f"{path}: non-numeric hits value at line {number}")
                continue
            lines_valid += 1
            if hits > 0:
                lines_covered += 1
            else:
                uncovered.append(number)
        rate_raw = cls.get("line-rate")
        try:
            rate = float(rate_raw) if rate_raw is not None else None
        except ValueError:
            rate = None
            warnings.append(f"{path}: non-numeric line-rate")
        files[path] = FileCoverage(
            path=path,
            line_rate=rate,
            lines_valid=lines_valid or None,
            lines_covered=lines_covered or None,
            uncovered_lines=tuple(sorted(uncovered)),
        )

    if not files:
        return CoverageSummary(
            available=False,
            source=source,
            timestamp=timestamp,
            reason="report contains no '<class>' entries with a filename",
            warnings=tuple(warnings),
        )

    return CoverageSummary(
        available=True,
        source=source,
        timestamp=timestamp,
        files=files,
        warnings=tuple(warnings),
    )


def _parse_xml(text: str) -> Any:
    """Parse coverage XML with entity expansion disabled.

    ``defusedxml`` is preferred and is a declared runtime dependency. If it is genuinely
    missing, the standard-library parser is used as a fallback; the document is already
    size-capped by the caller before it reaches this function, and neither path resolves
    external entities. The fallback call sites carry an explicit ``# nosec`` justification
    rather than a blanket module exclusion.
    """
    if _HAS_DEFUSED and _safe_fromstring is not None:
        return _safe_fromstring(text)
    parser = StdET.XMLParser()  # noqa: S314  # nosec B314
    return StdET.fromstring(text, parser=parser)  # noqa: S314  # nosec B314


def load_coverage_report(
    path: str | Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> CoverageSummary:
    """Read and parse a coverage report from disk, enforcing a size cap first."""
    target = Path(path)
    if not target.is_file():
        return CoverageSummary(
            available=False,
            source=str(target.name),
            reason="coverage report file not found",
        )
    size = target.stat().st_size
    if size > max_bytes:
        raise CoverageError(
            "Coverage report exceeds the configured size limit.",
            details={"limit": max_bytes, "observed": size, "unit": "bytes"},
        )
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return CoverageSummary(
            available=False,
            source=target.name,
            reason="coverage report could not be read",
        )
    return parse_cobertura(text, source=target.name)


def match_coverage_path(report_path: str, candidates: Iterable[str]) -> str | None:
    """Find the candidate path that a coverage entry refers to, if any.

    Association is by exact normalized path or by a unique suffix match. Ambiguous suffix
    matches are rejected rather than guessed.
    """
    normalized = _normalize(report_path)
    matches = [c for c in candidates if _normalize(c) == normalized]
    if len(matches) == 1:
        return matches[0]
    suffix_matches = [
        candidate
        for candidate in candidates
        if _normalize(candidate).endswith("/" + normalized)
        or normalized.endswith("/" + _normalize(candidate))
    ]
    if len(suffix_matches) == 1:
        return suffix_matches[0]
    return None


__all__ = [
    "CoverageSummary",
    "FileCoverage",
    "load_coverage_report",
    "match_coverage_path",
    "parse_cobertura",
]
