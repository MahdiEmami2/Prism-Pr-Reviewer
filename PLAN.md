# PRISM — PLAN.md

Project: **PRISM: Intelligent Pull Request Reviewer**
Working directory: `/home/user/prism`
Plan status: live document, updated at the end of every phase.

---

## 0. Specification provenance (patch A.6)

- A PRISM functional specification was **not supplied** with the task prompt.
- Per patch A.1–A.5 the specification is therefore a **draft specification**, created from
  the requirements explicitly present in the task prompt.
- Provenance of every requirement: `DRAFT-SPEC`, derived from the numbered sections of
  "PRISM — Autonomous Software Engineering Master Prompt".
- File: `docs/SPEC.md` (contains a `Missing details` section listing every gap and the
  conservative default chosen).
- All requirements in `docs/REQUIREMENT_TRACEABILITY.md` carry the `DRAFT-SPEC` tag and may
  not be reported as PASS against an original user intent that was never supplied.

---

## Phase A — Environment inspection (COMPLETE)

Commands were run in `/home/user/prism` on 2026-10-17 (UTC). Verbatim results:

| Check | Command | Result |
|---|---|---|
| Python | `python3 --version` | `Python 3.12.3` (`/usr/bin/python3`) |
| Git | `git --version` | `git version 2.43.0` |
| pip | `python3 -m pip --version` | `pip 24.0 from /usr/lib/python3/dist-packages/pip (python 3.12)` |
| pytest | `python3 -m pytest --version` | `pytest 9.1.1` |
| Ruff | `ruff --version` | **MISSING before install** → installed, see below |
| Bandit | `bandit --version` | **MISSING before install** → installed, see below |
| Docker | `docker --version` | **MISSING** (`docker: command not found`) |
| Codex CLI | `codex --version` | **MISSING** |
| Network | `httpx.get('https://pypi.org/simple/')` | HTTP 200 (PyPI reachable) |
| CPUs | `nproc` | 2 |
| RAM | `free -m` | 1989 MB total, 1779 MB available |
| Pre-existing files | `ls -la /home/user` | only environment files + `PRISM_MASTER_PROMPT_v2.1.md`; no prior PRISM work to preserve |

Installed for this project (network available, PyPI reachable):

- `ruff`, `bandit`, `fastapi`, `uvicorn`, `pytest-cov`, `pytest-asyncio`, `respx`
- already present: `httpx 0.28.1`, `pydantic 2.14.1`, `pytest 9.1.1`

Environment limitations carried forward as documented blockers:

- **Docker is not installed.** The Dockerfile and Compose file will be validated statically
  only; the container build cannot be executed here. Status: BLOCKED (environment), see
  `evidence/H-docker.txt`.
- **Codex CLI is not installed.** Per section 17, a documented self-review is performed
  instead; no extra tool is installed for this.

Licence decision (stated assumption, not a question to the user): **MIT**. Chosen because it
is the most common permissive licence for a portfolio/educational tool, imposes no
copyleft obligation on the sample project, and is a standard, pre-existing text.

---

## Phase B — Configuration, models, rule registry, diff parsing

- [ ] `prism/core/config.py` — settings from environment, safe defaults, size limits
- [ ] `prism/core/types.py` — severity/confidence enums + documented semantics
- [ ] `prism/core/exceptions.py` — typed error hierarchy
- [ ] `prism/core/logging_setup.py` — logging with secret redaction filter
- [ ] `prism/core/redaction.py` — token/secret redaction helper
- [ ] `prism/core/limits.py` — input size, file count, timeout, response size caps
- [ ] `prism/diff/parser.py` — unified diff parser (add/modify/delete/rename/binary)
- [ ] `prism/diff/mapping.py` — new-side line mapping and per-file reconstruction
- [ ] `prism/analyzers/base.py` + `registry.py` — plugin rule system

## Phase C — Deterministic analyzers and finding normalization

- [ ] AST-based Python rules with FP guards (`analyzers/python_rules.py`)
- [ ] Credential pattern rules with placeholder safeguards (`analyzers/secrets.py`)
- [ ] Test-awareness heuristics (`analyzers/test_awareness.py`)
- [ ] Optional Ruff/Bandit adapter with return-code checking (`analyzers/external.py`)
- [ ] `findings/normalize.py`, `dedupe.py`, `identity.py` — stable IDs

## Phase D — Reporting and local diff review

- [ ] Markdown report with escaping and dynamic code fences
- [ ] JSON report with stable schema
- [ ] CLI `review-diff`

## Phase E — GitHub retrieval and FastAPI

- [ ] `github/urls.py` — strict host/repo/PR validation
- [ ] `github/client.py` — read-only client, pagination, rate limits, size caps
- [ ] `github/pr_diff.py` — build FileDiff objects from the files API
- [ ] `api/app.py`, `api/routes.py`, `api/schemas.py` — 4 documented endpoints

## Phase F — Test-awareness, hardening, limits

- [ ] Cobertura XML reader with safe XML handling
- [ ] Input limits, error taxonomy, threat-model controls

## Phase G — Documentation, CI, Docker

- [ ] README (English) + German summary, rule catalog, sample report
- [ ] CONTRIBUTING / SECURITY / CHANGELOG / LICENSE / .env.example
- [ ] docs: ARCHITECTURE, THREAT_MODEL, ANALYSIS_RULES, TESTING, DATA_PRIVACY, ACCEPTANCE_CRITERIA, REQUIREMENT_TRACEABILITY
- [ ] `.github/workflows/ci.yml` with minimal `permissions:`
- [ ] Dockerfile, .dockerignore, docker-compose.yml (static validation only)

## Phase H — Tests, lint, security, self-review

- [ ] pytest + coverage with real captured output in `evidence/`
- [ ] `ruff check`, `ruff format --check`, `bandit -r` with real output
- [ ] Regression tests for every bug found during development
- [ ] Documented self-review (Codex CLI unavailable)

## Phase I — Release

- [ ] Run PRISM against `samples/sample_project`, save diff + MD + JSON reports
- [ ] Build `dist/PRISM.zip`, `unzip -t`, inspect contents, grep for secrets
- [ ] Completion report with only executed claims

---

## Checkpoints

Checkpoint log is appended below as each phase closes (patch F.1/F.4).

### Checkpoint A — 2026-10-17

- phase: A
- completed: environment inspection; tool installation; licence decision; SPEC draft created; project tree created
- blockers: Docker unavailable (attempt 1 of max 3 — alternative: static validation of Dockerfile, no further attempts needed); Codex CLI unavailable (attempt 1 — alternative: documented self-review)
- gates touched: AC-ENV → PASS (table above), AC-DOCKER-BUILD → BLOCKED (environment)
- next task: Phase B — core config, types, diff parser
- next command: `python3 -m pytest -q`

---

## Phase B–G completion (recorded 2026-10-17)

| Phase | Status | Real outcome |
| --- | --- | --- |
| B — config, models, registry, diff parsing | COMPLETE | `prism/core` (config, types, exceptions, limits, redaction, logging), `prism/diff` (parser + line mapping), `prism/findings` (models, identity, dedupe, policy), `prism/analyzers/registry.py` with duplicate-ID enforcement. Verified by `tests/test_diff_parser.py` and `tests/test_findings.py`. |
| C — deterministic analyzers + normalisation | COMPLETE | 15 AST rules (`PY001`–`PY015`), 3 secret rules (`SEC001`–`SEC003`), 3 testing rules (`TST001`–`TST003`). Each has positive, negative and boundary/malformed tests. Stable IDs derived without line numbers. |
| D — reporting + local diff review | COMPLETE | Markdown (ten fixed sections, emitted even on an empty review) and deterministic JSON. CLI `review-diff` reads a diff file, stdin, or a local git range. |
| E — GitHub retrieval + FastAPI | COMPLETE | Read-only client with `Link` pagination, rate-limit and size handling, patch→diff conversion; five endpoints. All GitHub HTTP calls use `httpx.MockTransport`. |
| F — test awareness, hardening, limits | COMPLETE | Cobertura ingestion with line-explicit matching only; diff/patch/file/page/response caps with typed errors; request-body middleware; host allow-list; token redaction; report-injection sanitisation. |
| G — documentation, CI, Docker config | COMPLETE (Docker execution BLOCKED) | 17-section README + German portfolio summary, `PLAN.md`, six docs plus the traceability matrix, CONTRIBUTING/SECURITY/CHANGELOG/LICENSE, hardened Dockerfile and Compose, CI with `permissions: contents: read`. Docker is not installed in this environment, so the image was **not built here**: the configuration was validated statically (`evidence/H-ci-static.txt`) and is built in CI. |

## Phase H — quality gates (real output, this session)

See `evidence/H-pytest.txt`, `evidence/H-ruff.txt`, `evidence/H-ruff-format.txt`,
`evidence/H-bandit.txt`, `evidence/H-ci-static.txt`. The exact counts are quoted in the
completion report rather than duplicated here, so there is one authoritative copy.

## Phase I — release

`dist/PRISM.zip` built from the intended source set, integrity-checked with `unzip -t`,
listed with `unzip -l`, and grepped for `.env`, `.git` and token patterns. Evidence:
`evidence/I-zip.txt`, `evidence/I-zip-grep.txt`.

### Checkpoint H/I — 2026-10-17

- phase: H and I
- completed: full suite, coverage, `ruff check`, `ruff format --check`, bandit, static CI/Docker
  validation, example regeneration by a real PRISM run, release archive
- blockers: Docker unavailable (attempt 1 of max 3 — alternative: static validation, then CI);
  Codex CLI unavailable (attempt 1 — alternative: documented self-review)
- gates touched: every code gate PASS from executable evidence; AC-DOCKER-BUILD BLOCKED
  (environment); dependency-CVE scanning PARTIAL (documented gap, `docs/THREAT_MODEL.md` T9)
- next task: none required. Optional follow-ups are listed in `CHANGELOG.md` under Unreleased.
