# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Additional languages (JavaScript/TypeScript, Go) behind the existing rule registry.
- Per-repository configuration file (`.prism.toml`) as an alternative to environment variables.
- A measured evaluation harness for the heuristic rules, so false-positive rates can be reported
  as numbers rather than adjectives.
- SARIF output for native code-scanning integration.
- Dependency-vulnerability scanning in CI (currently a stated gap, not a claim).

## [0.1.0] — 2026-10-17

First release. Everything below was implemented and verified in this release; nothing is
listed as "done" that was not executed.

### Added — review inputs
- Unified-diff parser handling added, modified, deleted, renamed and binary file entries,
  multi-hunk location mapping, CRLF input, quoted paths containing spaces, and the
  `\ No newline at end of file` marker.
- Local Git mode that reads `git diff` output (fixed argv, `shell=False`, explicit timeout).
- GitHub pull-request mode over the official REST API: owner/repo/number, anonymous access for
  public repositories, optional read-only token, `Link`-header pagination, and conversion of
  API patches into the same internal diff model.

### Added — analysis rules
- 15 Python rules based on the standard-library `ast` module: `PY001` mutable default argument,
  `PY002` bare `except`, `PY003` swallowed exception, `PY004` `shell=True`, `PY005` dynamic code
  execution, `PY006` unsafe deserialisation, `PY007` unsafe `yaml.load`, `PY008` `os.system` /
  `os.popen`, `PY009` `tempfile.mktemp`, `PY010` weak hash, `PY011` disabled TLS verification,
  `PY012` unreachable statement, `PY013` missing timeout (heuristic), `PY014` syntax error in an
  added file, `PY015` assertion used for validation.
- 3 secret rules: `SEC001` hard-coded credential with placeholder safeguards and value masking,
  `SEC002` PEM private-key material, `SEC003` high-entropy literal (heuristic).
- 3 testing rules: `TST001` source changed without a test change (heuristic), `TST002` uncovered
  changed line per a supplied report, `TST003` changed file absent from the coverage report.
- Plugin rule registry with uniqueness enforcement, so adding a rule needs no engine change.

### Added — finding quality
- Stable finding identity derived from rule, normalised path, symbol and normalised signature —
  deliberately independent of line numbers.
- Deduplication by identity with an auditable merge log; distinct problems in one file are kept
  distinct.
- Independent severity and confidence dimensions with published meanings.
- Configurable minimum severity, rule exclusions and severity overrides, with a record of every
  suppression and the policy that caused it.

### Added — test awareness
- Configurable test-file conventions (pytest defaults, including `conftest.py`).
- Cobertura XML ingestion with line-explicit association only.
- Explicit statements when coverage is missing or does not mention a changed file; PRISM never
  derives a percentage from a test-file count.

### Added — reporting
- Markdown report with the ten required sections, always present in the same order, including
  when there are no findings.
- JSON report with a fixed schema and byte-identical repeat runs (`generated_at` is opt-in).
- Untrusted-content sanitisation: Markdown escaping, HTML neutralisation, control-character
  stripping, table-cell escaping, and code fences that outgrow any backtick run in the content.

### Added — interfaces
- CLI: `review-diff`, `review-github`, `rules`, `version`.
- FastAPI service: `GET /health`, `GET /version`, `GET /api/v1/rules`,
  `POST /api/v1/reviews/diff`, `POST /api/v1/reviews/github`, with Pydantic models, a body-size
  middleware, a single error envelope and a route inventory containing no executor.

### Added — security
- Host allow-list and URL construction in one place; `https` only; traversal-rejecting path
  segments; `ref` validation.
- Token read from the environment only, used only in the `Authorization` header, redacted in
  logs and absent from every summary, error body and report.
- Size and pagination limits with typed errors; response-size cap applied before JSON parsing.
- Hardened, entity-expansion-resistant coverage XML parsing.
- Optional Ruff/Bandit adapters that are off by default and report tool failure explicitly.

### Added — optional extension points
- LLM provider interface with a `NullProvider`. No provider ships, so no key is needed and no AI
  accuracy is claimed. Contract documented: schema-validated output, diff re-validation of paths
  and lines, `heuristic` labelling, and no ability to suppress a deterministic finding.

### Added — project infrastructure
- `pyproject.toml` with constrained dependencies, pytest and coverage configuration, and a full
  Ruff rule set.
- Dockerfile (multi-stage, non-root, no compiler at runtime) and a hardened Compose service.
- GitHub Actions CI with minimal permissions, lint, tests on Python 3.10–3.12, Bandit, container
  build and a tracked-`.env` check.
- Documentation: README (with a German project summary), `PLAN.md`, `docs/SPEC.md`,
  `docs/ACCEPTANCE_CRITERIA.md`, `docs/ARCHITECTURE.md`, `docs/ANALYSIS_RULES.md`,
  `docs/THREAT_MODEL.md`, `docs/TESTING.md`, `docs/DATA_PRIVACY.md`,
  `docs/REQUIREMENT_TRACEABILITY.md`, `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE`, `.env.example`.
- An intentionally flawed sample project with a clean counterpart, plus a generated diff and
  example reports produced by an actual PRISM run.

### Known limitations in this release
- Static analysis only; runtime behaviour cannot be proven.
- Findings are limited to changed lines.
- A modified file is analysed from its added-lines fragment; constructs depending on unchanged
  surrounding context can be missed (always reported).
- Python-only AST analysis; other languages receive credential-pattern checks only.
- The container build could not be executed in the environment where this release was prepared
  because Docker was not installed there; it is built in CI.
