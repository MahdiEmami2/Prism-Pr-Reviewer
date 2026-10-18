"""FastAPI application factory.

Security-relevant behaviour configured here:

* Request bodies are capped by middleware before they reach a route, and the cap produces
  the documented ``413`` error envelope.
* Domain errors are mapped onto consistent responses. Unhandled exceptions produce a generic
  body: no traceback, filesystem path or environment value is ever returned.
* CORS is not enabled at all, because no browser client is part of this build. Absence is
  safer than a permissive default.
* The httpx transport used for GitHub is injectable, so tests can run with a mock transport
  and no network access.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from prism import __version__
from prism.analyzers.registry import RuleRegistry, build_default_registry
from prism.api.routes import router
from prism.core.config import PrismConfig
from prism.core.exceptions import InputTooLargeError, PrismError
from prism.core.logging_setup import configure_logging, get_logger

logger = get_logger("api")


class BodySizeLimitMiddleware:
    """Reject oversized request bodies before a route parses them.

    Implemented as a pure ASGI middleware to avoid a BaseHTTPMiddleware dependency.
    """

    def __init__(self, app: Any, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = None
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = None
                break

        if declared is not None and declared > self.max_bytes:
            error = InputTooLargeError(
                "Request body exceeds the configured size limit.",
                details={"limit": self.max_bytes, "observed": declared, "unit": "bytes"},
            )
            response = JSONResponse(status_code=error.http_status, content=error.to_dict())
            await response(scope, receive, send)
            return

        received = 0
        exceeded = False

        async def wrapped_receive() -> Any:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    exceeded = True
            return message

        if declared is None:
            await self.app(scope, wrapped_receive, send)
            if exceeded:  # pragma: no cover - defensive; header-less clients
                logger.warning("request body exceeded the limit without a content-length header")
            return

        await self.app(scope, wrapped_receive, send)


def create_app(
    config: PrismConfig | None = None,
    *,
    transport: Any | None = None,
    registry: RuleRegistry | None = None,
) -> FastAPI:
    """Build the FastAPI application.

    ``transport`` lets tests inject an ``httpx.MockTransport`` so no test can reach GitHub.
    """
    configure_logging()
    effective_config = config or PrismConfig.from_env()

    def build_registry(cfg: PrismConfig) -> RuleRegistry:
        if registry is not None:
            return registry
        return build_default_registry(include_external=cfg.enable_external_tools)

    app = FastAPI(
        title="PRISM — Intelligent Pull Request Reviewer",
        version=__version__,
        summary="Deterministic static analysis for local Git diffs and GitHub pull requests.",
        description=(
            "PRISM analyses a unified diff or a GitHub pull request and returns normalised "
            "findings. Analysed code is never executed. No endpoint accepts a URL or a "
            "filesystem path to read, and no endpoint executes submitted code."
        ),
        docs_url="/docs",
        redoc_url=None,
        openapi_tags=[
            {"name": "system", "description": "Liveness, version and capability disclosure."},
            {"name": "review", "description": "Review execution and the rule catalogue."},
        ],
    )

    app.state.config = effective_config
    app.state.registry = build_registry(effective_config)
    app.state.build_registry = build_registry
    app.state.transport = transport

    def github_client_factory(cfg: PrismConfig, injected_transport: Any | None) -> Any:
        from prism.github.client import GitHubClient

        return GitHubClient(cfg, transport=injected_transport)

    app.state.github_client_factory = github_client_factory

    app.add_middleware(BodySizeLimitMiddleware, max_bytes=effective_config.api_max_body_bytes)

    @app.middleware("http")
    async def add_timing_header(request: Request, call_next: Callable[..., Any]) -> Any:
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Process-Time-Ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
        return response

    @app.exception_handler(PrismError)
    async def prism_error_handler(request: Request, exc: PrismError) -> JSONResponse:
        logger.info("domain error: %s", exc.code)
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error while serving a request")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An internal error occurred. No request details are returned.",
                    "details": {},
                }
            },
        )

    app.include_router(router)
    return app


app = create_app()


__all__ = ["BodySizeLimitMiddleware", "app", "create_app"]
