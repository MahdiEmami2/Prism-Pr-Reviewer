"""Report generation: Markdown (human) and JSON (machine)."""

from prism.reporting.json_report import render_json
from prism.reporting.markdown import render_markdown
from prism.reporting.sanitize import (
    escape_markdown,
    fence_for,
    inline_code,
    safe_text,
)

__all__ = [
    "escape_markdown",
    "fence_for",
    "inline_code",
    "render_json",
    "render_markdown",
    "safe_text",
]
