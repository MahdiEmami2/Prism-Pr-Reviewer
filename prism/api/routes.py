"""FastAPI routes.

Documented endpoints:

* ``GET  /health``                - liveness plus capability flags (no secrets, no paths)
* ``GET  /version``               - version, rule IDs, limitations
* ``POST /api/v1/reviews/diff``   - analyse an inline unified diff
* ``POST /api/v1/reviews/github`` - analyse a pull request by owner/repo/number
* ``GET  /api/v1/rules``          - the rule catalogue

Deliberately absent: any endpoint that executes submitted code, reads a caller-supplied
path, or fetches a caller-supplied URL. The GitHub endpoint accepts coordinates only; the
URL is built from an allow-listed host.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from prism import __version__
from prism.api.schemas import (
    DiffReviewRequest,
    GitHubReviewRequest,
    HealthResponse,
    ReviewResponse,
    VersionResponse,
)
from prism.core.exceptions import PrismError
from prism.core.logging_setup import get_logger
from prism.core.types import ReviewMode
from prism.engine.review import ReviewEngine
from prism.reporting.json_report import schema_summary

logger = get_logger("api")

router = APIRouter()

API_VERSION = "v1"


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(request: Request) -> HealthResponse:
    """Report liveness and which optional capabilities are enabled."""
    app = request.app
    registry = app.state.registry
    return HealthResponse(
        status="ok",
        version=__version__,
        rule_count=len(registry.rule_specs()),
        github_token_configured=bool(app.state.config.has_github_token),
        external_tools_enabled=bool(app.state.config.enable_external_tools),
    )


@router.get("/version", response_model=VersionResponse, tags=["system"])
def version(request: Request) -> VersionResponse:
    """Report the version, implemented rules and honest limitations."""
    app = request.app
    registry = app.state.registry
    return VersionResponse(
        name="PRISM",
        version=__version__,
        api_version=API_VERSION,
        json_schema_version=schema_summary()["schema_version"],
        supported_review_modes=[mode.value for mode in ReviewMode],
        implemented_rule_ids=list(registry.rule_ids()),
        optional_features={
            "external_tools_enabled": bool(app.state.config.enable_external_tools),
            "llm_extension_enabled": bool(app.state.config.enable_llm_extension),
            "coverage_ingestion": True,
        },
        limitations=[
            "Static analysis only; analysed code is never executed.",
            "Findings are limited to changed lines.",
            "No LLM provider ships with this build.",
            "PRISM never posts review comments; publishing is a separate operation that this "
            "build does not perform.",
        ],
    )


@router.get("/api/v1/rules", tags=["review"])
def rules(request: Request) -> dict[str, Any]:
    """Return the machine-readable rule catalogue."""
    return {"success": True, "rules": request.app.state.registry.catalog()}


@router.post("/api/v1/reviews/diff", response_model=ReviewResponse, tags=["review"])
def review_diff(payload: DiffReviewRequest, request: Request) -> Any:
    """Analyse an inline unified diff."""
    from prism.diff.parser import parse_unified_diff
    from prism.engine.review import ReviewEngine

    config = request.app.state.config.with_overrides(
        min_severity=payload.options.min_severity,
        excluded_rules=tuple(payload.options.excluded_rules),
        include_generated_at=payload.options.include_generated_at,
    )
    registry = request.app.state.build_registry(config)
    parsed = parse_unified_diff(
        payload.diff,
        max_bytes=config.max_diff_bytes,
        max_files=config.max_files,
        max_patch_bytes=config.max_patch_bytes,
    )
    engine = ReviewEngine(config=config, registry=registry)
    result = engine.analyze(
        parsed,
        mode=ReviewMode.DIFF,
        metadata={"title": payload.title or "uploaded diff", "source": "api"},
    )
    body = result.to_dict(include_confidence_meaning=payload.options.include_confidence_meaning)
    return {"success": True, "review": body}


@router.post("/api/v1/reviews/github", response_model=ReviewResponse, tags=["review"])
def review_github(payload: GitHubReviewRequest, request: Request) -> Any:
    """Analyse a pull request identified by owner, repository and number."""
    from prism.github.diff_source import files_from_github
    from prism.github.urls import RepoTarget, validate_owner, validate_pull_number, validate_repo

    config = request.app.state.config.with_overrides(
        min_severity=payload.options.min_severity,
        excluded_rules=tuple(payload.options.excluded_rules),
        include_generated_at=payload.options.include_generated_at,
    )
    target = RepoTarget(
        owner=validate_owner(payload.owner),
        repo=validate_repo(payload.repo),
        pull_number=validate_pull_number(payload.pull_number),
    )
    transport = request.app.state.transport
    with request.app.state.github_client_factory(config, transport) as client:
        info = client.get_pull_request(target)
        entries = []
        notes: list[dict[str, Any]] = []
        for page_entries, truncated in client.iter_pull_request_files(
            target, max_files=config.max_files
        ):
            entries.extend(page_entries)
            if truncated:
                notes.append(
                    {
                        "path": None,
                        "reason": "file_limit_reached",
                        "detail": "the pull request has more files than the configured limit",
                    }
                )
    parsed = files_from_github(
        entries,
        max_files=config.max_files,
        max_patch_bytes=config.max_patch_bytes,
        additional_notes=notes,
    )
    registry = request.app.state.build_registry(config)
    engine = ReviewEngine(config=config, registry=registry)
    result = engine.analyze(
        parsed,
        mode=ReviewMode.GITHUB,
        metadata=info.to_metadata(),
    )
    body = result.to_dict(include_confidence_meaning=payload.options.include_confidence_meaning)
    return {"success": True, "review": body}


def error_response(error: PrismError) -> JSONResponse:
    """Convert a domain error into the consistent error envelope."""
    return JSONResponse(status_code=error.http_status, content=error.to_dict())


__all__ = ["API_VERSION", "error_response", "router"]
