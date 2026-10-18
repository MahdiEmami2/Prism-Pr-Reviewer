# syntax=docker/dockerfile:1
#
# Multi-stage build. The runtime stage contains only the application and its runtime
# dependencies: no compiler, no test tooling, no build cache, no secrets.
#
# PRISM analyses untrusted input, so the container runs as a non-root user, drops the
# ability to write anywhere except /tmp, and never executes analysed code (there is no
# eval, no import of analysed files and no subprocess call that runs repository code).

# ---------------------------------------------------------------- build stage
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY pyproject.toml README.md ./
COPY prism ./prism
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
 && pip install --no-cache-dir .

# ---------------------------------------------------------------- runtime stage
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="PRISM — Intelligent Pull Request Reviewer" \
      org.opencontainers.image.description="Deterministic static analysis for local git diffs and GitHub pull requests." \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    PRISM_HTTP_TIMEOUT_SECONDS=20

RUN groupadd --system --gid 10001 prism \
 && useradd --system --uid 10001 --gid prism --home-dir /app --shell /usr/sbin/nologin prism

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY prism /app/prism
COPY docs /app/docs
COPY pyproject.toml README.md LICENSE /app/

USER prism:prism

# No credentials are baked in. Supply PRISM_GITHUB_TOKEN at runtime if you need one.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import json,urllib.request;print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/health'))['status'])" || exit 1

# uvicorn binds to all interfaces inside the container; publish the port deliberately.
CMD ["uvicorn", "prism.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
