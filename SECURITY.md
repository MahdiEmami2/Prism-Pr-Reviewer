# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |

## Reporting a vulnerability

Please **do not** open a public issue for a security problem. Instead, report it privately to
the maintainer of the repository you obtained PRISM from, including:

- PRISM version (`python -m prism version`) and Python version,
- the exact command or request that triggers the issue,
- a description of the impact,
- a minimal reproduction (redacted — never include a live token or private source code),
- any suggested fix.

You can expect an acknowledgement and an assessment of severity. No response-time guarantee is
offered, because this project has no security team.

## Security properties this tool claims

These are the properties PRISM is designed and tested to hold. They are stated so that a
reviewer can check them, not as a guarantee.

| Property | How it holds | Test |
| --- | --- | --- |
| Analysed code is never executed | `ast.parse` only; no import, no `eval`, no `exec`, no repository runtime | `tests/test_python_rules.py::test_analyzers_never_import_or_execute_the_analysed_module` |
| Repository content is never treated as instructions | Rules match text; there is no LLM in the loop | `tests/test_python_rules.py::test_analysed_code_cannot_inject_instructions_into_the_report` |
| Tokens are never logged or reported | Environment-only read; header-only use; redaction filter; no value in any summary | `tests/test_secrets.py`, `tests/test_github.py` |
| Only allow-listed hosts are contacted | Single URL-construction control point; `https` only; segments validated; the API accepts coordinates, not URLs | `tests/test_github.py`, `tests/test_api.py` |
| No path from a diff is ever opened | Paths are data; `..` collapsed for identity | `tests/test_api.py::test_path_traversal_shaped_diff_path_is_handled_without_touching_disk` |
| Hostile content cannot restructure a report | Escaping, control-character stripping, fence growth beyond the content's own backtick run | `tests/test_reporting.py` |
| No shell string is built from untrusted values | Fixed argv lists, `shell=False`; refs and paths validated | `tests/test_external_tools.py`, `tests/test_github.py` |
| Limits bound resource use | Diff/patch/file/response/page caps, HTTP timeout, body-size middleware, container limits | `tests/test_diff_parser.py`, `tests/test_api.py`, `tests/test_coverage.py` |
| Nothing is published | No GitHub write method exists in the client | `tests/test_api.py::test_no_endpoint_executes_submitted_code` (route inventory) |

## Known residual risks

Stated honestly; see `docs/THREAT_MODEL.md` §4 for the full list.

1. **Fragment analysis can miss context.** A modified file is analysed from its added lines;
   a construct split across an unchanged line may be missed. Always surfaced in
   `scope.diagnostics`.
2. **Heuristic false positives.** `PY013`, `SEC003` and `TST001` correlate rather than prove.
   They carry `low` confidence and are never presented as facts.
3. **No dependency-CVE scanning in this build.** Bandit (SAST) runs in CI; a dependency
   vulnerability scanner is a roadmap item, not a current claim.
4. **Coverage staleness is unverifiable.** A supplied report may describe a different revision.
5. **The API has no authentication.** Do not expose it to an untrusted network without
   placing authentication in front of it.
6. **Container hardening was not executed here.** Docker was unavailable in the build
   environment; the configuration is statically validated and built in CI.

## What PRISM does not do

- It does not post review comments, push commits, or change repository settings.
- It does not run analysed code, install dependencies from a reviewed repository, or execute
  repository scripts.
- It does not send code to any third-party service. There is no LLM provider in this build.
- It does not guarantee that a clean report means the code is secure. It means no configured
  rule matched within the documented scope.

## Handling a report

A PRISM report contains file paths and short code snippets from the reviewed change. Treat it
as you would treat the patch itself: do not commit reports from private repositories into
public ones.
