"""PRISM command-line interface.

Modes:

* ``prism review-diff --diff-file <path>``       analyse a saved unified diff
* ``prism review-diff --repo <path>``            analyse a local Git working tree
* ``prism review-github --owner O --repo R --pull N``   analyse a pull request
* ``prism rules``                                print the rule catalogue
* ``prism version``                              print the version

Every command writes the Markdown and/or JSON report where asked. Nothing is published.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from prism import __version__
from prism.analyzers.registry import build_default_registry
from prism.core.config import PrismConfig
from prism.core.exceptions import PrismError
from prism.core.logging_setup import configure_logging, get_logger
from prism.core.types import ReviewMode
from prism.diff.parser import ParsedDiff, parse_local_git_diff, parse_unified_diff
from prism.engine.review import ReviewEngine
from prism.reporting.json_report import render_json
from prism.reporting.markdown import render_markdown

logger = get_logger("cli")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prism",
        description="PRISM — Intelligent Pull Request Reviewer (static analysis only).",
    )
    parser.add_argument("--version", action="version", version=f"PRISM {__version__}")
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: INFO).")
    sub = parser.add_subparsers(dest="command", required=True)

    diff = sub.add_parser("review-diff", help="Review a unified diff or a local Git repository.")
    source = diff.add_mutually_exclusive_group(required=True)
    source.add_argument("--diff-file", help="Path to a unified diff file ('-' for stdin).")
    source.add_argument("--repo", help="Path to a local Git repository.")
    diff.add_argument("--base", help="Base revision for a local Git diff.")
    diff.add_argument("--head", help="Head revision for a local Git diff.")
    diff.add_argument("--markdown", help="Write the Markdown report to this path.")
    diff.add_argument("--json", dest="json_path", help="Write the JSON report to this path.")
    diff.add_argument("--coverage", help="Path to a Cobertura XML coverage report.")
    diff.add_argument("--min-severity", default=None, help="Minimum severity to report.")
    diff.add_argument(
        "--exclude-rule", action="append", default=[], help="Rule ID to exclude (repeatable)."
    )
    diff.add_argument(
        "--external-tools",
        action="store_true",
        help="Also run Ruff and Bandit when they are installed (off by default).",
    )

    gh = sub.add_parser("review-github", help="Review a GitHub pull request.")
    gh.add_argument("--owner", required=True)
    gh.add_argument("--repo", required=True)
    gh.add_argument("--pull", required=True, type=int)
    gh.add_argument("--markdown", help="Write the Markdown report to this path.")
    gh.add_argument("--json", dest="json_path", help="Write the JSON report to this path.")
    gh.add_argument("--min-severity", default=None)
    gh.add_argument("--exclude-rule", action="append", default=[])

    sub.add_parser("rules", help="Print the rule catalogue as JSON.")
    sub.add_parser("version", help="Print the version.")
    return parser


def _config_from_args(args: argparse.Namespace) -> PrismConfig:
    config = PrismConfig.from_env()
    changes: dict[str, Any] = {}
    if getattr(args, "min_severity", None):
        changes["min_severity"] = args.min_severity
    if getattr(args, "exclude_rule", None):
        merged = tuple(dict.fromkeys((*config.excluded_rules, *args.exclude_rule)))
        changes["excluded_rules"] = merged
    if getattr(args, "external_tools", False):
        changes["enable_external_tools"] = True
    if getattr(args, "coverage", None):
        changes["coverage_report_path"] = args.coverage
    return config.with_overrides(**changes)


def _load_coverage(config: PrismConfig) -> dict[str, Any]:
    if not config.coverage_report_path:
        return {"available": False, "reason": "no coverage report was supplied"}
    from prism.coverage.cobertura import load_coverage_report

    summary = load_coverage_report(config.coverage_report_path, max_bytes=config.max_coverage_bytes)
    payload = summary.to_dict()
    payload["files"] = {path: entry.to_dict() for path, entry in summary.files.items()}
    return payload


def _run_review(
    parsed: ParsedDiff, config: PrismConfig, metadata: dict[str, Any]
) -> tuple[str, str]:
    from prism.core.types import ToolStatus
    from prism.findings.models import ToolReport

    tools = []
    if config.enable_external_tools:
        tools.append(
            ToolReport(
                name="external_tools",
                status=ToolStatus.UNAVAILABLE.value,
                detail=(
                    "enabled, but this build only runs Ruff/Bandit against files on disk; the "
                    "diff was analysed in memory, so no file-based scan was performed"
                ),
            )
        )
    registry = build_default_registry(include_external=config.enable_external_tools)
    engine = ReviewEngine(config=config, registry=registry)
    result = engine.analyze(
        parsed,
        mode=ReviewMode((parsed.source == "github" and ReviewMode.GITHUB) or ReviewMode.DIFF),
        metadata=metadata,
        coverage=_load_coverage(config),
        tools=tools,
    )
    return render_markdown(result), render_json(result)


def _read_diff_file(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8", errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level)

    try:
        if args.command == "version":
            print(f"PRISM {__version__}")
            return 0
        if args.command == "rules":
            registry = build_default_registry()
            print(json.dumps(registry.catalog(), indent=2, ensure_ascii=False))
            return 0

        config = _config_from_args(args)

        if args.command == "review-diff":
            if args.diff_file is not None:
                text = _read_diff_file(args.diff_file)
                parsed = parse_unified_diff(
                    text,
                    max_bytes=config.max_diff_bytes,
                    max_files=config.max_files,
                    max_patch_bytes=config.max_patch_bytes,
                )
                metadata = {
                    "title": Path(args.diff_file).name if args.diff_file != "-" else "stdin",
                    "source": "local_diff",
                }
            else:
                parsed = parse_local_git_diff(
                    args.repo,
                    base=args.base,
                    head=args.head,
                    max_bytes=config.max_diff_bytes,
                    timeout_seconds=config.http_timeout_seconds,
                )
                metadata = {
                    "title": f"local git diff in {Path(args.repo).name}",
                    "source": "local_git",
                    "base": args.base or "(working tree)",
                    "head": args.head or "(working tree)",
                }
            markdown, json_text = _run_review(parsed, config, metadata)

        elif args.command == "review-github":
            from prism.github.client import fetch_pull_request
            from prism.github.diff_source import files_from_github

            info, entries, notes = fetch_pull_request(
                args.owner, args.repo, args.pull, config=config
            )
            parsed = files_from_github(entries, max_files=config.max_files, additional_notes=notes)
            markdown, json_text = _run_review(parsed, config, info.to_metadata())
        else:  # pragma: no cover - argparse enforces the command set
            parser.error("unknown command")
            return 2

        if args.markdown:
            Path(args.markdown).parent.mkdir(parents=True, exist_ok=True)
            Path(args.markdown).write_text(markdown, encoding="utf-8")
            print(f"Markdown report written to {Path(args.markdown).name}")
        else:
            print(markdown)
        if args.json_path:
            Path(args.json_path).parent.mkdir(parents=True, exist_ok=True)
            Path(args.json_path).write_text(json_text, encoding="utf-8")
            print(f"JSON report written to {Path(args.json_path).name}")
        return 0

    except PrismError as exc:
        print(f"error: {exc.code}: {exc.message}", file=sys.stderr)
        if exc.details:
            print(f"details: {json.dumps(exc.details, ensure_ascii=False)}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
