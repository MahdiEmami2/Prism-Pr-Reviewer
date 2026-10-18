"""Coverage report ingestion."""

from prism.coverage.cobertura import (
    CoverageSummary,
    FileCoverage,
    load_coverage_report,
    parse_cobertura,
)

__all__ = [
    "CoverageSummary",
    "FileCoverage",
    "load_coverage_report",
    "parse_cobertura",
]
