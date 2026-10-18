"""Generate the committed example reports from the demonstration diff.

Run through ``samples/sample_project/generate_diff.sh``, or directly:

    python3 samples/sample_project/make_reports.py

The reports are produced by an actual PRISM run, not written by hand. ``demo_data`` is set in
the report metadata so that a reader (and ``tests/test_sample_project.py``) can tell that the
findings refer to deliberately planted problems in the sample, not to a third-party
repository.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from prism.core.config import PrismConfig  # noqa: E402
from prism.core.types import ReviewMode  # noqa: E402
from prism.diff.parser import parse_unified_diff  # noqa: E402
from prism.engine.review import ReviewEngine  # noqa: E402
from prism.reporting.json_report import render_json  # noqa: E402
from prism.reporting.markdown import render_markdown  # noqa: E402

DIFF_PATH = REPO_ROOT / "examples" / "sample_diff.patch"
MARKDOWN_PATH = REPO_ROOT / "examples" / "sample_report.md"
JSON_PATH = REPO_ROOT / "examples" / "sample_report.json"

METADATA = {
    "title": "PRISM demonstration project (sample, not a real repository)",
    "source": "local_diff",
    "demo_data": True,
}


def main() -> int:
    """Analyse the sample diff and write both reports. Returns a process exit code."""
    if not DIFF_PATH.is_file():
        print(f"error: {DIFF_PATH} does not exist; run generate_diff.sh first", file=sys.stderr)
        return 2

    config = PrismConfig()
    parsed = parse_unified_diff(
        DIFF_PATH.read_text(encoding="utf-8"),
        max_bytes=config.max_diff_bytes,
        max_files=config.max_files,
        max_patch_bytes=config.max_patch_bytes,
    )
    result = ReviewEngine(config=config).analyze(parsed, mode=ReviewMode.DIFF, metadata=METADATA)

    MARKDOWN_PATH.write_text(render_markdown(result), encoding="utf-8")
    JSON_PATH.write_text(render_json(result), encoding="utf-8")

    rule_ids = sorted({finding.rule_id for finding in result.findings})
    print(f"findings: {len(result.findings)} across {len(rule_ids)} rule(s)")
    print("rules:    " + ", ".join(rule_ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
