# PRISM — Acceptance Criteria

Requirement IDs refer to `docs/SPEC.md` (provenance `DRAFT-SPEC`).
Status vocabulary is fixed by patch B.6 and is **not** paraphrased:

- **PASS:** verified by execution
- **PARTIAL:** implemented but incompletely verified
- **BLOCKED:** cannot proceed due to a documented blocker
- **NOT IMPLEMENTED:** missing functionality

A criterion is satisfied only by actual evidence recorded per patch §E. A criterion with no
evidence is at best PARTIAL and must state what is unverified.

---

## Gates

| Gate | Requirement | Acceptance criterion (falsifiable) | Evidence required |
|---|---|---|---|
| AC-ENV | R-04 | Python, Git, pip versions and the availability of ruff/bandit/docker are captured before any code is written | `PLAN.md` §Phase A table |
| AC-SPEC | R-04 / patch A | A specification exists, is labelled `DRAFT`, and lists every missing detail with a default | `docs/SPEC.md` |
| AC-DIFF-ADD | R-07 | An "added file" unified diff is parsed to status `added` with correct new-side line numbers | `tests/test_diff_parser.py` |
| AC-DIFF-MOD | R-07 | A modified-file diff maps added lines to the correct new-file line numbers across multiple hunks | `tests/test_diff_parser.py` |
| AC-DIFF-DEL | R-07 | A deleted file is parsed as `deleted` and produces no line-anchored findings | `tests/test_diff_parser.py` |
| AC-DIFF-REN | R-07 | A rename is parsed as `renamed` with both paths, and findings use the new path | `tests/test_diff_parser.py` |
| AC-DIFF-BIN | R-05/R-08 | A binary file entries produce a `skipped` record, not a parse error | `tests/test_diff_parser.py` |
| AC-RULE-POS | R-09 | Every registered rule fires on at least one crafted positive snippet | `tests/test_python_rules.py`, `tests/test_secrets.py` |
| AC-RULE-NEG | R-09 | Every registered rule stays silent on crafted negative snippets | `tests/test_python_rules.py`, `tests/test_secrets.py` |
| AC-RULE-MAL | R-16 | Malformed input (empty diff, truncated hunk, non-UTF-8 bytes, huge line) yields a diagnostic and never an unhandled exception | `tests/test_diff_parser.py` |
| AC-SYNTAX | R-09 | An added file that does not parse is reported as a definite syntax problem; a partial patch that does not parse is reported as a scope diagnostic, not a finding | `tests/test_python_rules.py` |
| AC-ID | R-10 | The same finding keeps the same `finding_id` when unrelated lines are inserted above it (line numbers move) | `tests/test_findings.py` |
| AC-DEDUP | R-10 | Duplicate findings collapse to one; distinct problems in one file stay distinct | `tests/test_findings.py` |
| AC-SEV-CONF | R-10 | Severity and confidence are independent and validated; an unknown value is rejected | `tests/test_findings.py` |
| AC-THRESH | R-10 | A configured severity threshold filters findings, and rule exclusions remove exactly the excluded rule | `tests/test_findings.py` |
| AC-FIXED-DET | R-10 | Two runs over identical input produce byte-identical JSON output | `tests/test_reporting.py` |
| AC-ESC | R-12 | Untrusted content (backticks, fences, HTML, table pipes, control characters, script tags) cannot break out of the report structure | `tests/test_reporting.py` |
| AC-JSON | R-12 | The JSON report validates against the documented schema and round-trips | `tests/test_reporting.py` |
| AC-MD-SEC | R-12 | The Markdown report contains every one of the 10 required sections | `tests/test_reporting.py` |
| AC-GH-PAGE | R-08 | Pagination follows `Link: rel="next"` and stops at the page cap | `tests/test_github.py` |
| AC-GH-RATE | R-08 | A 403/429 rate-limit response raises a typed error carrying the reset time; no token value appears in the message | `tests/test_github.py` |
| AC-GH-NOPATCH | R-08 | A file entry without a `patch` key becomes a `skipped` record with a reason | `tests/test_github.py` |
| AC-GH-HOST | R-14 | Non-GitHub hosts, path traversal and malformed repo/PR identifiers are rejected | `tests/test_github.py` |
| AC-GH-MOCK | R-16 | The whole standard test suite runs with mocked HTTP; no live token and no network needed | `tests/conftest.py` guard + full-suite run |
| AC-API-VAL | R-13 | Invalid payloads return a consistent error shape with HTTP 422/400/413 as appropriate | `tests/test_api.py` |
| AC-API-LEAK | R-13 | No response contains a filesystem path or an environment value | `tests/test_api.py` |
| AC-API-EXEC | R-13 | No endpoint executes submitted code (asserted by endpoint inventory) | `tests/test_api.py` |
| AC-SEC-REDACT | R-14 | Tokens are redacted in logs and reports; `GITHUB_TOKEN` never appears in output | `tests/test_secrets.py` |
| AC-LIMITS | R-08 | Oversized diff, too many files, oversized patch and too-large response each raise an explicit typed error/limit diagnostic | `tests/test_diff_parser.py` |
| AC-COV-MISS | R-11 | A missing coverage report yields "unavailable" and never a percentage | `tests/test_coverage.py` |
| AC-COV-MAP | R-11 | Coverage is associated only with files present in the report | `tests/test_coverage.py` |
| AC-COV-NOINFER | R-11 | No code path derives a coverage percentage from a count of test files | code review note + `tests/test_coverage.py` |
| AC-TESTHEUR | R-11 | "Source changed without test changes" is emitted as a heuristic with low confidence and heuristic flag set | `tests/test_coverage.py` |
| AC-AST-SAFE | R-14 | Analysers never import or execute analysed modules (asserted by a test module that would raise if imported) | `tests/test_python_rules.py` |
| AC-NOEVAL | R-14 | `eval`/`exec` are not called anywhere in PRISM's own source (static scan) | `evidence/H-security.txt` (bandit) + grep evidence |
| AC-EXT-OPT | R-09 | Ruff/Bandit integration is optional, checks availability and return codes, and surfaces tool failure as a diagnostic instead of silence | `tests/test_external_tools.py` |
| AC-LINT | R-16 | `ruff check` and `ruff format --check` exit 0 | `evidence/H-ruff-check.txt`, `evidence/H-ruff-format.txt` |
| AC-BANDIT | R-16 | `bandit -r prism` exit code and findings recorded verbatim | `evidence/H-bandit.txt` |
| AC-PYTEST | R-16 | The full suite passes; the recorded test count and coverage come from that run | `evidence/H-pytest.txt` |
| AC-CI | R-17 | The workflow declares minimal permissions and never uses `pull_request_target` to run untrusted code | static check recorded in `evidence/H-docker.txt` |
| AC-DOCKER | R-17 | Dockerfile/Compose/`.dockerignore` validated statically; a real build is **BLOCKED** because Docker is not installed | `evidence/H-docker.txt` |
| AC-ENVFILE | R-17 | `.env.example` contains placeholders only | `tests/test_external_tools.py` |
| AC-DEMO | R-19 | The sample project diff, Markdown report and JSON report are produced by an actual PRISM run and are labelled demonstration data | `examples/` + `evidence/I-demo.txt` |
| AC-ZIP | R-21 | `dist/PRISM.zip` exists, `unzip -t` reports no errors, contains source/tests/docs, and contains no `.git`, `.env`, virtualenv, cache or credential | `evidence/I-zip.txt` |
| AC-TRACE | patch G | Every requirement ID maps to implementation and test/evidence with a status label | `docs/REQUIREMENT_TRACEABILITY.md` |
| AC-HONEST | patch B | The completion report uses only the four status labels and quotes only executed results | completion report |

---

## Non-goals (explicit, so absence is not a defect)

- No database, frontend framework, message broker or microservice split (R-05).
- No posting comments, pushing or changing GitHub settings (R-04 §10).
- No LLM provider is implemented or contacted (R-15, M-8).
- No performance, coverage-threshold, certification or security-guarantee claims (R-18).
- No execution of analysed code, ever (R-09, R-14).
