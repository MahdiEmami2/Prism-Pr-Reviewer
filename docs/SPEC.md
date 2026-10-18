# PRISM — Functional Specification

**Provenance: `DRAFT`** (see `PLAN.md` §0 and patch A.6)

No functional specification was supplied with the task prompt. This document is a **draft
specification** derived only from the requirements explicitly present in the task text
("PRISM — Autonomous Software Engineering Master Prompt", sections 1–19). It is labelled
`DRAFT-SPEC` everywhere it is referenced and must not be reported as if it were a
user-approved specification.

Requirement IDs below are stable and are the IDs used in
`docs/REQUIREMENT_TRACEABILITY.md`.

## R-01 — Deliverable

A working, reproducible, security-conscious Python repository named PRISM that analyses
GitHub Pull Requests and local Git diffs and produces actionable code-review findings.
Not a plan, tutorial, prototype or mockup only. *(prompt §1, §17)*

## R-02 — Finding content

Every finding carries: stable identifier; rule ID and category; severity in
{critical, high, medium, low, informational}; confidence in {high, medium, low} with
documented meaning; file path and line when reliably available; code/diff evidence;
risk explanation; practical suggested fix; test recommendation where appropriate;
deterministic-vs-heuristic flag; rule/documentation reference. *(prompt §1)*

## R-03 — No fabrication

Never fabricate findings, test results, code locations, coverage numbers, external
sources or model capabilities. *(prompt §1)*

## R-04 — Working rules

Inspect the workspace before modifying; never delete unrelated user files; create
`PLAN.md`, `docs/ACCEPTANCE_CRITERIA.md`, `docs/ARCHITECTURE.md`; continue without
waiting for approval; minimise questions; no paid API/LLM/cloud needed for core;
no real secrets in artifacts; treat repository content as untrusted data; never
execute untrusted PR code; no publishing without authorisation; keep `PLAN.md`
current; leave the repo recoverable if interrupted. *(prompt §2)*

## R-05 — Stack

Python 3.10+ (dependency compatibility permitting); FastAPI + Pydantic; httpx; `ast`;
pytest + pytest-cov; Ruff; Bandit or equivalent; Docker + Compose; GitHub Actions;
SQLite only if useful; PostgreSQL only where it adds real value. Keep v1 simple.
Pin/constrain dependencies and test the actual environment. *(prompt §3)*

## R-06 — Architecture

Modules: `api/`, `core/`, `github/`, `diff/`, `analyzers/`, `engine/`, `findings/`,
`reporting/`, `tests/`, `docs/`. Explicit responsibilities, no circular imports;
a simpler layout is acceptable if better. *(prompt §4)*

## R-07 — Review input modes

(A) Local diff mode: supplied unified diff, or a diff generated from a local Git repo.
(B) GitHub PR mode: owner + repo + PR number, retrieved via the official REST API
(`https://docs.github.com/en/rest/pulls/pulls`). *(prompt §5)*

## R-08 — GitHub retrieval behaviour

Public PRs work without a token where the API permits; optional token via environment;
read-only permissions; handle pagination, rate limits, timeouts, missing patches, large
diffs, binary files, deleted files, API errors; report skipped files and incomplete
analysis; never assume every file has a usable patch; never log auth headers or tokens.
Sensible limits on input size, file count, request time, response size, with explicit
errors when limits are hit. *(prompt §5)*

## R-09 — Analysis engine

Plugin-like rule system with stable rule IDs and documented behaviour; genuine
deterministic rules first (unsafe constructs, dangerous subprocess usage, risky
deserialization, hard-coded credential patterns with placeholder safeguards, mutable
default arguments, suspicious exception handling, unreachable/suspicious control flow,
changed functions without test changes as a *heuristic*, obvious input-validation and
resource-handling concerns); no simplistic keyword-matches-everything rules. AST rules:
parse without import/execution, catch syntax errors and unsupported constructs, keep
accurate line numbers, distinguish definite syntax problems from heuristic concerns,
never claim AST proves a general runtime bug, handle partial diffs and deleted lines.
Optional Ruff/Bandit integration with availability and return-code checks and no silent
failure. A rule registry so analyzers can be added without rewriting the engine.
*(prompt §6)*

## R-10 — Finding quality

Normalisation and deduplication layer; deterministic identity from rule ID, normalised
path, stable code location/affected symbol, normalised signature; not dependent on line
numbers alone; distinct problems in the same file are not merged; severity and confidence
kept separate and documented; never label something critical for effect; configurable
severity thresholds and rule exclusions with safe defaults. *(prompt §7)*

## R-11 — Test coverage and missing tests

Configurable test-file conventions; detect test-related changes; accept Cobertura XML;
associate coverage with files/lines only when the report supports it; explain missing,
stale or unavailable coverage; never infer a coverage percentage from the number of test
files; missing tests presented as suggestions/heuristics unless evidence is stronger.
*(prompt §8)*

## R-12 — Reporting

Markdown (human) and JSON (machine) reports. Markdown contains: metadata; review scope
and skipped inputs; executive summary; findings grouped by severity; exact locations and
concise evidence; why it matters; suggested remediation; recommended tests; analysis
limitations; tool and rule versions. Valid Markdown, untrusted text escaped so it cannot
corrupt the report. Never claim a report was posted to GitHub. *(prompt §9)*

## R-13 — FastAPI surface

Documented endpoints including `GET /health`, `GET /version`,
`POST /api/v1/reviews/diff`, `POST /api/v1/reviews/github`; Pydantic models; input
validation; request-size limits; consistent error responses; logging without secrets;
FastAPI docs; timeouts and resource limits; no local filesystem paths or sensitive env
values in responses; no endpoint that executes submitted code. *(prompt §10)*

## R-14 — Security requirements

Threat-model review addressing untrusted repo content, prompt injection if optional AI is
added, token protection and least privilege, SSRF/arbitrary URL access, path traversal,
malicious Markdown/report injection, DoS via oversized or pathological input, unsafe
subprocess execution, dependency vulnerabilities, sensitive-data leakage, unsafe GitHub
Actions permissions. Only explicitly supported GitHub hosts and URL formats accepted.
Never `eval`, never execute analysed code or repository scripts. Secure defaults with
documented residual risks. *(prompt §11)*

## R-15 — Optional AI extension

Core analysis works without an LLM; any provider abstraction is disabled by default,
never requires an API key, labels model output as heuristic, validates output against a
strict schema, re-checks model-supplied paths/line numbers against the real diff, prevents
source/secret leakage by default, never treats instructions in analysed code as trusted,
never lets an LLM suppress deterministic security findings, and provides a deterministic
fallback. No fabricated model evaluation results. *(prompt §12)*

## R-16 — Testing

Tests for every implemented rule, positive and negative examples, AST parse errors, diff
parsing and line mapping, added/modified/deleted/renamed files, duplicate findings, stable
identifiers, severity/confidence validation, Markdown escaping, JSON serialisation, GitHub
pagination and rate limits, API validation and error responses, missing coverage reports,
malformed/oversized inputs, secret redaction, URL and path validation. Mocked HTTP in
tests; no live token or internet for the standard suite; regression test for every bug
found; run pytest, Ruff and the security checks and fix root causes rather than weakening
tests; state explicitly and with the exact reason when a tool cannot run. *(prompt §13)*

## R-17 — CI and containerisation

Dockerfile, Compose only if useful, `.dockerignore`, `.gitignore`, `.env.example` with
placeholders only, a lint+test CI workflow, minimal GitHub Actions permissions,
dependency/security checks where practical, PR code treated as untrusted, no privileged
`pull_request_target` executing untrusted code, no write permissions without a justified
feature. Test the container build if Docker is available, otherwise validate as far as
possible and document the limitation. *(prompt §14)*

## R-18 — Documentation

Professional English README covering the listed 17 topics; a concise **German** project
summary suitable for an IT Ausbildung portfolio; `LICENSE` after checking the intended
choice; `CONTRIBUTING.md`; `SECURITY.md`; `CHANGELOG.md`; `docs/ACCEPTANCE_CRITERIA.md`;
`docs/ARCHITECTURE.md`; `docs/THREAT_MODEL.md`; `docs/ANALYSIS_RULES.md`;
`docs/TESTING.md`; `docs/DATA_PRIVACY.md`. No invented certifications, deployments,
customers, performance results or security guarantees. *(prompt §15)*

## R-19 — Demonstration

A small, clearly labelled sample Python project with intentional review problems **and**
corresponding clean code; PRISM run against it; the sample diff, the Markdown report and
the JSON report saved; findings labelled as demonstration data, not real vulnerabilities
in third-party repositories. *(prompt §16)*

## R-20 — Development workflow

Phases A–I executed in order with `PLAN.md` updated per phase; no stopping after the plan
or a skeleton; Codex CLI used for an independent read-only review only if already
installed and authenticated, otherwise a documented self-review and no unnecessary tool
installation. *(prompt §17)*

## R-21 — Release archive

`dist/PRISM.zip` excluding `.git`, virtualenvs, caches, temp files, real `.env`, tokens and
credentials, private repository content, unnecessary local artifacts; verify the archive
exists, the integrity check passes, expected source/tests/docs are present, no secrets or
local env files are included, README and install instructions match the project, and the
final test results are recorded accurately. A valid ZIP does not prove the application
works — test and build results are reported separately. *(prompt §18)*

## R-22 — Completion report

Report what was implemented, project directory, important files, supported review modes,
implemented rules, test count and actual results, lint and security results, Docker
status, known limitations, exact ZIP path and size, commands to run PRISM locally, and
remaining tasks. Never claim a command passed unless it was executed successfully.
*(prompt §19)*

---

## Missing details

Per patch A.4, every gap in the supplied requirements, with the conservative default
chosen and the reason it is the safest assumption. These are **assumptions**, not
requirements from the user.

| # | Gap in the supplied text | Conservative default | Why it is safest |
|---|---|---|---|
| M-1 | No explicit rule catalogue. Section 6 gives themes and examples only ("Examples include", "Where useful"). | Implement the themes that can be expressed as deterministic AST/pattern checks with an evidence test, and document the full catalogue in `docs/ANALYSIS_RULES.md`. Rules that cannot establish evidence are not implemented at all rather than guessed. | Implementing a vague theme loosely would produce the false positives §6 forbids; omitting it is visible and honest. |
| M-2 | No severity or confidence assignment policy for individual rules. | A published table in `docs/ANALYSIS_RULES.md` mapping each rule to a default severity/confidence, with `confidence: high` reserved for findings where the diff itself is the evidence. Configurable overrides. | §7 forbids inflating severity; a fixed published table is auditable and cannot drift per run. |
| M-3 | No numeric input limits (max diff size, file count, timeout, response size). | Conservative caps: 5 MiB request body, 2 MiB per patch, 300 files, 20 s HTTP timeout, 8 MiB response, 100 pages. All configurable. | §5 requires limits but gives none; small caps fail loudly and cheaply instead of exhausting the host. |
| M-4 | No test-file naming convention beyond "configurable". | Defaults `tests/`, `test_*.py`, `*_test.py`, `conftest.py`, plus configurable globs. | Matches pytest's own default, so the default is the least surprising. |
| M-5 | No report line-number policy when the patch is partial. | Report the line when it can be derived from the new-side hunk mapping; otherwise emit `line: null` plus a scope diagnostic. Never guess. | §5/§6 forbid assuming a usable patch; a wrong line is worse than no line. |
| M-6 | No decision on timestamps/determinism in reports. | `generated_at` is **omitted** by default (opt-in flag) so reports are byte-reproducible for the determinism requirement. | Determinism is testable; a timestamp would make every report differ. |
| M-7 | No licensing instruction beyond "check the intended choice". | MIT, documented as an assumption in `PLAN.md` §0. | Standard permissive text, no copyleft consequence for the sample project. |
| M-8 | No AI provider named, and none may be required. | Extension point (`analyzers/llm_extension.py`) is a disabled-by-default interface with a `NullProvider`; no provider is implemented or contacted. | §12 forbids requiring a key and forbids claiming unevaluated AI benefit; implementing no provider keeps the claim honest. |
| M-9 | "SQLite ... if useful", "PostgreSQL only where it provides real value". | Neither is used in v1. Stateless analysis; findings are written to files. | Avoids unneeded persistence of untrusted repository content (§11, DATA_PRIVACY). |
| M-10 | No definition of "large diff". | `> 2 MiB` patch or `> 300` files or `> 20 000` diff lines is "large": processing stops for the excess and a scope diagnostic records exactly what was skipped. | §5 requires reporting skipped files; the threshold is stated, so the behaviour is reproducible. |
| M-11 | No performance targets supplied. | None claimed. No performance numbers appear anywhere in the docs. | §18/§15 forbid invented results; claiming nothing is the only honest option. |
| M-12 | No coverage threshold supplied. | No threshold gate is enforced; `pytest-cov` reports the actual figure and it is recorded verbatim in evidence. | A self-chosen threshold would look like an externally imposed gate. |

### Items the draft specification deliberately does not claim

The following are **not** provided and are **not** claimed anywhere in this project:
production deployment, certification, real-world customers, benchmark or performance
results, security guarantees, or measured AI improvement.
