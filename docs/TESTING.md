# Testing

## 1. How to run

```bash
python -m pytest -q                                      # full suite
python -m pytest -q --no-header                          # quiet, no header
python -m pytest --cov=prism --cov-report=term-missing   # with coverage
python -m pytest -m "not integration" -q                 # skip opt-in network tests
python -m pytest tests/test_python_rules.py -q           # one file
```

Quality gates:

```bash
ruff check prism tests
ruff format --check prism tests
bandit -r prism -ll
```

## 2. Test design rules

These are enforced by convention and checked in review:

1. **Meaningful assertions only.** A test that merely asserts "no exception" or "result is
   non-empty" does not satisfy the requirement. Every rule test asserts the rule ID, and where
   it matters the confidence value and evidence class.
2. **A positive and a negative case per rule.** The negative case must be the *compliant*
   variant of the same code, not unrelated code.
3. **Boundary and malformed cases** for each rule family: empty diff, truncated hunk,
   unparseable hunk header, NUL bytes, CRLF, no-newline marker, a 200 000-character line,
   oversized patch, too many files, empty coverage report, malformed XML.
4. **Regression tests for discovered bugs**, named after the bug (see §5).
5. **No weakening.** Assertions are never relaxed and tests are never deleted to make the
   suite green; root causes are fixed instead.

## 3. Test files and what each one pins

| File | Covers |
| --- | --- |
| `tests/conftest.py` | Shared fixtures, the diff builders, and the autouse network guard |
| `tests/test_diff_parser.py` | Added/modified/deleted/renamed/binary entries, multi-hunk line mapping, CRLF, quoted paths with spaces, malformed hunks, NUL bytes, long lines, every configured limit, full-source vs fragment reconstruction |
| `tests/test_python_rules.py` | Positive, negative and boundary cases for PY001–PY015; syntax-error handling; out-of-scope filtering; AST safety; injection resistance; rule-catalogue integrity |
| `tests/test_secrets.py` | Positive, negative and placeholder-safeguard cases for SEC001–SEC003; entropy and placeholder helpers; masking; redaction in logs, mappings and configuration |
| `tests/test_findings.py` | Path and signature normalisation; ID stability under line movement; ID uniqueness across rules/paths/signatures; deduplication; severity/confidence independence; thresholds, exclusions and overrides; config parsing |
| `tests/test_reporting.py` | All ten Markdown sections; empty-review rendering; fence growth; table integrity under a hostile filename; control-character stripping; JSON schema, byte-identical repeat runs, optional timestamp, suppression visibility |
| `tests/test_github.py` | URL/host/traversal validation; ref validation; metadata parsing; token presence and absence; 401/403/404/429 handling; pagination via `Link`; page cap; file cap; oversized response; non-JSON body; patch → diff conversion for added/deleted/renamed/binary; end-to-end PR review with a mocked transport; parity between PR and local-diff review |
| `tests/test_api.py` | All five endpoints; OpenAPI inventory; validation errors; unknown-field rejection; 413 body cap; per-request policy; injected mock transport; no path/env leakage; no executor endpoint; consistent error envelope |
| `tests/test_coverage.py` | Cobertura parsing; missing/malformed/empty/wrong-root reports; non-numeric values; size cap; line-explicit coverage findings; test-path conventions; the TST001 heuristic including truncation |
| `tests/test_external_tools.py` | Ruff/Bandit adapters when installed; missing executable; timeout; unexpected exit code; unparseable output; off-by-default enforcement; `.env.example` placeholder integrity |
| `tests/test_sample_project.py` | The demonstration project: the risky file must trigger the expected rule set; the clean file must produce **zero** findings; placeholder configuration must produce no credential findings |
| `tests/test_integration_optin.py` | Live GitHub checks, skipped unless `PRISM_RUN_INTEGRATION=1` |

## 4. Test isolation and secrets

- **Network is blocked by default.** The autouse `_block_network` fixture in `conftest.py`
  replaces `socket.socket.connect` with a guard that raises for any address other than
  loopback. A test that tried to reach GitHub would fail loudly rather than silently depend on
  the internet. GitHub behaviour is exercised through `httpx.MockTransport`.
- **No credentials.** The suite never reads a real token. Tests that need a token-shaped value
  use an obvious dummy (`ghp_abcdefghijklmnopqrstuvwxyz012345`) and assert that the value is
  *not* disclosed in summaries, errors or evidence.
- **No writes to GitHub.** No test issues a non-`GET` request; the client has no write method.
- **No analysed code execution.** Tests assert the property directly, including a fixture
  module whose import would abort the process.
- **Opt-in only for the live tests.** They are marked `integration` and skipped unless
  `PRISM_RUN_INTEGRATION=1`; they also need network access.

## 5. Regression tests added for bugs found during development

Each of these pins a defect that was found and fixed, not a hypothetical:

| Bug found | Regression test |
| --- | --- |
| Skip records were rendered as raw `dataclass` reprs inside the scope table instead of the path/reason/detail columns | `tests/test_reporting.py::test_markdown_lists_limitations_and_scoped_skips` |
| Suppressed findings were filtered out but never passed to the result, so the JSON report showed no `suppressed_findings` | `tests/test_reporting.py::test_suppressed_findings_are_visible_in_the_json_report` |
| An unescaped `\|` in a file path added a column to every table row, producing a ragged table | `tests/test_reporting.py::test_hostile_filename_does_not_break_the_table` |
| Keyword-only defaults (`def f(*, cache={})`) were not inspected, so PY001 missed them | `tests/test_python_rules.py::test_py001_boundary_kwonly_default_and_dict_default` |
| `PRISM_MIN_SEVERITY` from the environment was stored as a raw string, so `min_severity=medium` compared as text and filtered the wrong findings | `tests/test_findings.py::test_config_from_env_parses_and_validates` |
| A hunk content line beginning with `--- ` (for example `-- removed separator`) was skipped as if it were a file header, losing removed lines | `tests/test_diff_parser.py::test_a_removed_line_starting_with_dashes_is_not_mistaken_for_a_header` |
| Combined merge diffs (`diff --cc`) produced a generic "not a diff" error instead of the specific unsupported-input guidance | `tests/test_diff_parser.py::test_combined_merge_diff_is_rejected_with_guidance` |
| `conftest.py` was not a test file by default, so test-only reviews triggered the "no test change" heuristic | `tests/test_coverage.py::test_conftest_is_a_test_file_by_default` |
| Ref validation did not reject whitespace, tilde or caret, which git forbids in ref names | `tests/test_github.py::test_ref_validation_rejects_control_characters_and_whitespace` |
| A test fixture reused the literal `abcdefghij`, which the placeholder guard correctly silenced — the guard was right and the test was wrong | `tests/test_secrets.py::test_is_placeholder_is_a_first_class_guarantee` |
| `prism/engine/review.py` built a `ToolReport` then immediately returned it as a `dict`, producing an invalid type in the report | `tests/test_external_tools.py::test_tool_reports_are_rendered_in_the_markdown_report` |
| Dead helper code in the engine (`_assignment` with an unreachable branch, unused helpers) | `ruff check` (F401/B012 class) — the lint gate is the regression test here |

## 6. Coverage

Coverage is reported as a measurement, **not** as a threshold gate: the requirement text
specifies no target, so asserting a self-chosen number would look like an externally imposed
criterion. The exact figure from the final run is recorded verbatim in `evidence/` and quoted
in the completion report.

## 7. Environment limitations

| Tool | Status in the build environment | Consequence |
| --- | --- | --- |
| Docker | **not installed** | The image build could not be executed; Dockerfile and Compose were validated statically and are built in CI. Recorded as BLOCKED, not as PASS. |
| Codex CLI | **not installed** | Per the task instructions, a documented self-review was performed instead and no extra tool was installed. |
| Network | available (PyPI reachable) | Live GitHub tests remain opt-in anyway, so the standard suite has no network dependency. |
