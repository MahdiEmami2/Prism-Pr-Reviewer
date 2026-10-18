<a id="readme-top"></a>

<div align="center">

<picture>
  <source media="(prefers-color-scheme: light)" srcset="assets/prism-wordmark-light.svg">
  <img src="assets/prism-wordmark-dark.svg" alt="PRISM — Intelligent Pull Request Reviewer" width="610">
</picture>

**Evidence-first code review for diffs and GitHub pull requests — deterministic, offline, auditable.**

[Install](#5-installation) · [Local diff](#6-local-diff-usage) · [GitHub PR](#7-github-pr-usage) · [API](#8-api-examples) · [Rules](#10-rule-catalog) · [Security](#14-security-and-privacy-notes) · [Limitations](#15-limitations) · [Deutsch](#projektzusammenfassung-deutsch)

</div>

# PRISM — Intelligent Pull Request Reviewer

[![CI](https://img.shields.io/badge/CI-lint%20%2B%20tests-blue)](.github/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)

![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Pytest](https://img.shields.io/badge/tests-pytest-ad1457)
![Ruff](https://img.shields.io/badge/lint-ruff-bf4b00)
![Bandit](https://img.shields.io/badge/security-bandit-b71c1c)
![Docker](https://img.shields.io/badge/Docker-ready-2496ed?logo=docker&logoColor=white)
![Offline](https://img.shields.io/badge/runs-offline-455a64)
![No LLM](https://img.shields.io/badge/LLM-none-6a1b9a)

PRISM reviews a **unified diff** or a **GitHub Pull Request** and returns normalised,
citable code-review findings: what changed, why it matters, how to fix it, and how strongly
the evidence supports the claim.

Core analysis is deterministic and runs entirely offline. There is no LLM, no paid API and
no cloud dependency. PRISM never imports, compiles or executes the code it reviews.

## At a glance

| | |
| --- | --- |
| 🔍 **Evidence first** | A rule fires only when the construct is in the *changed lines*. |
| 🎯 **Honest confidence** | Severity (impact) and confidence (evidence strength) are separate dimensions. |
| 🆔 **Stable identity** | Finding IDs ignore line numbers, so a moved finding keeps its ID. |
| 🧾 **Scope reporting** | Skipped files, unparsable patches and reached limits are always reported. |
| 🔒 **Safe by design** | Offline, read-only, never executes the reviewed code. |
| 📄 **Reproducible output** | Markdown and JSON reports; identical input gives byte-identical JSON. |

> [!NOTE]
> PRISM makes no coverage, performance or AI-quality claims it cannot back with evidence. See [Limitations](#15-limitations).

<details>
<summary><strong>Table of contents</strong></summary>

1. [Project overview](#1-project-overview)
2. [Problem and solution](#2-problem-and-solution)
3. [Feature list](#3-feature-list)
4. [Architecture](#4-architecture)
5. [Installation](#5-installation)
6. [Local diff usage](#6-local-diff-usage)
7. [GitHub PR usage](#7-github-pr-usage)
8. [API examples](#8-api-examples)
9. [Configuration](#9-configuration)
10. [Rule catalog](#10-rule-catalog)
11. [Sample report](#11-sample-report)
12. [Testing and quality checks](#12-testing-and-quality-checks)
13. [Docker instructions](#13-docker-instructions)
14. [Security and privacy notes](#14-security-and-privacy-notes)
15. [Limitations](#15-limitations)
16. [Roadmap](#16-roadmap)
17. [Contribution guide](#17-contribution-guide)
18. [Projektzusammenfassung (Deutsch)](#projektzusammenfassung-deutsch)
19. [Licence](#licence)

</details>

---

## 1. Project overview

| Item | Value |
| --- | --- |
| Name | PRISM — Intelligent Pull Request Reviewer |
| Package | `prism` (`prism-reviewer` on install) |
| Language | Python 3.10+ (developed and tested on 3.12) |
| Entry points | CLI (`python -m prism …`) and HTTP API (FastAPI) |
| Review modes | Local unified diff, local Git working tree, GitHub Pull Request |
| Rules | 15 deterministic/heuristic Python rules, 3 secret rules, 3 testing rules |
| Persistence | None. Findings are written to files or returned in the API response |
| Licence | MIT (a stated assumption — see `PLAN.md` §0) |

## 2. Problem and solution

**Problem.** Reviewing a pull request by eye is slow and inconsistent. Grep-based "security
scanners" flag every occurrence of a keyword and bury the reviewer in noise; LLM reviewers
produce fluent text that cannot be audited or reproduced.

**Solution.** PRISM restricts itself to claims it can justify from the diff:

1. **Evidence first.** A deterministic rule only fires when the construct is present in the
   *changed lines* and its conclusion follows from the diff itself.
2. **Honest confidence.** Severity (impact) and confidence (strength of evidence) are
   separate, documented dimensions. A pattern that merely correlates is labelled
   `heuristic` and never presented as proof.
3. **Stable identity.** Finding IDs are derived from rule, path, symbol and a normalised
   signature — never from line numbers — so a finding keeps its identity when code moves.
4. **Scope reporting.** Every skipped file, unparsable patch and reached limit is reported.
   A short report can never be mistaken for a clean one.

## 3. Feature list

- **Two input modes** — a saved/generated unified diff, or a GitHub PR by owner/repo/number.
- **15 Python rules** built on the standard-library `ast` module: mutable defaults, bare
  `except`, swallowed exceptions, `shell=True`, `eval`/`exec`/`compile`, unsafe
  deserialisation, unsafe `yaml.load`, `os.system`/`os.popen`, `tempfile.mktemp`, weak
  hashes, disabled TLS verification, dead code after a terminating statement, missing
  timeouts, syntax errors in new files, `assert`-based validation.
- **3 secret rules** with placeholder safeguards, so `password = "changeme"` is silent while
  `password = "<a realistic literal>"` is reported — with the value masked.
- **3 testing rules** — source-changed-without-test-change (heuristic), uncovered changed
  lines from a Cobertura report, and files the report does not mention.
- **Cobertura XML ingestion** with line-explicit matching only. PRISM never converts a test
  file count into a coverage percentage.
- **Two report formats** — a 10-section Markdown report and a stable JSON document.
- **Deterministic output** — two runs over identical input produce byte-identical JSON.
- **Strict input validation** — allow-listed GitHub hosts, typed errors, request-size caps.
- **Optional** Ruff/Bandit adapters (off by default) that report tool failures instead of
  hiding them.

## 4. Architecture

```
prism/
├── api/          FastAPI app, routes, Pydantic schemas
├── core/         config, types, errors, limits, redaction, logging
├── diff/         unified-diff parser and changed-line mapping
├── github/       allow-listed URLs, read-only REST client, patch → diff
├── analyzers/    rule registry + AST rules, secret rules, test awareness, external tools
├── engine/       orchestration: diff in, normalised findings out
├── findings/     find model, identity, deduplication, policy filters
├── coverage/     Cobertura XML reader
├── reporting/    Markdown renderer, JSON renderer, sanitisation
└── cli.py        command-line interface
```

Data flow: `diff text → parse_unified_diff → analyze_parsed_diff → deduplicate → apply_policy
→ ReviewResult → Markdown / JSON / API response`.

<div align="center">
  <img src="assets/prism-pipeline.svg" alt="PRISM review pipeline: input, parse, analyze, deduplicate, apply policy, output" width="900">
  <p><em>The review pipeline, from diff text to report.</em></p>
</div>

Full detail, including the untrusted-input boundary and the decisions behind each module, is
in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## 5. Installation

Requires Python 3.10 or newer. Docker is optional.

### Windows PowerShell

```powershell
git clone https://github.com/example/prism.git
Set-Location prism

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

Copy-Item .env.example .env     # edit .env locally; never commit it
python -m pytest -q
```

If script execution is blocked, run
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first, or activate with
`.\.venv\Scripts\activate.bat`.

### Linux / macOS

```bash
git clone https://github.com/example/prism.git
cd prism

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

cp .env.example .env            # edit .env locally; never commit it
python -m pytest -q
```

## 6. Local diff usage

Review a saved diff file:

```bash
python -m prism review-diff \
    --diff-file examples/sample_diff.patch \
    --markdown report.md \
    --json report.json
```

Review a local Git working tree or a commit range (no repository code is executed — only
`git diff` output is read):

```bash
python -m prism review-diff --repo . --base main --head HEAD --markdown report.md
python -m prism review-diff --repo . --markdown report.md      # uncommitted changes
cat change.patch | python -m prism review-diff --diff-file -   # stdin
```

Useful flags:

| Flag | Effect |
| --- | --- |
| `--coverage path/to/coverage.xml` | Add line-explicit coverage statements |
| `--min-severity high` | Hide findings below the given severity |
| `--exclude-rule PY010 --exclude-rule TST001` | Exclude specific rules |
| `--external-tools` | Also run Ruff/Bandit if installed (off by default) |
| `--log-level DEBUG` | Verbose, secret-redacted logging |

## 7. GitHub PR usage

Public pull requests work **without** a token. A read-only token is only needed if you hit
the anonymous rate limit.

```bash
# No token: works for public repositories.
python -m prism review-github --owner python --repo cpython --pull 1 --markdown pr.md

# Optional read-only token, supplied through the environment only.
export PRISM_GITHUB_TOKEN=ghp_your_read_only_token      # Linux/macOS
$env:PRISM_GITHUB_TOKEN = "ghp_your_read_only_token"    # Windows PowerShell
python -m prism review-github --owner octocat --repo Hello-World --pull 1347 \
    --markdown pr.md --json pr.json
```

PRISM issues `GET` requests only, follows pagination, caps pages/files/response size, and
never sends the token anywhere except the `Authorization` header of the API request.

## 8. API examples

Start the service:

```bash
uvicorn prism.api.app:app --reload --port 8000
```

Interactive documentation is served at `http://127.0.0.1:8000/docs`.

```bash
# Liveness and capability flags (never reveals secrets or paths)
curl -s http://127.0.0.1:8000/health

# Version, implemented rules, limitations
curl -s http://127.0.0.1:8000/version

# Review an inline diff
curl -s -X POST http://127.0.0.1:8000/api/v1/reviews/diff \
  -H 'Content-Type: application/json' \
  -d '{"diff": "diff --git a/x.py b/x.py\nnew file mode 100644\n--- /dev/null\n+++ b/x.py\n@@ -0,0 +1,2 @@\n+def f(items=[]):\n+    return items\n"}'

# Review a GitHub pull request by coordinates (no URL field exists)
curl -s -X POST http://127.0.0.1:8000/api/v1/reviews/github \
  -H 'Content-Type: application/json' \
  -d '{"owner": "python", "repo": "cpython", "pull_number": 1}'
```

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/health` | GET | Liveness plus capability flags |
| `/version` | GET | Version, rule IDs, limitations |
| `/api/v1/rules` | GET | Machine-readable rule catalogue |
| `/api/v1/reviews/diff` | POST | Analyse a unified diff |
| `/api/v1/reviews/github` | POST | Analyse a PR by owner/repo/number |

Errors always use one envelope:

```json
{"error": {"code": "input_too_large", "message": "…", "details": {"limit": 5242880}}}
```

## 9. Configuration

All settings are optional and read from `PRISM_*` environment variables. See
[`.env.example`](.env.example) for placeholders.

| Variable | Default | Meaning |
| --- | --- | --- |
| `PRISM_GITHUB_TOKEN` | *(unset)* | Optional read-only GitHub token |
| `PRISM_MAX_DIFF_BYTES` | `5242880` | Reject larger diffs |
| `PRISM_MAX_PATCH_BYTES` | `2097152` | Skip larger single-file patches |
| `PRISM_MAX_FILES` | `300` | Stop parsing after this many files |
| `PRISM_MAX_RESPONSE_BYTES` | `8388608` | Reject larger GitHub responses |
| `PRISM_MAX_PAGES` | `100` | Pagination cap |
| `PRISM_HTTP_TIMEOUT_SECONDS` | `20` | Request and Git timeout |
| `PRISM_MIN_SEVERITY` | `informational` | Minimum severity to report |
| `PRISM_EXCLUDED_RULES` | *(empty)* | Comma-separated rule IDs to exclude |
| `PRISM_COVERAGE_REPORT` | *(unset)* | Cobertura XML path |
| `PRISM_ENABLE_EXTERNAL_TOOLS` | `false` | Enable Ruff/Bandit adapters |
| `PRISM_ENABLE_LLM_EXTENSION` | `false` | Enable the (empty) LLM extension point |
| `PRISM_INCLUDE_GENERATED_AT` | `false` | Add a timestamp to reports |

`PRISM_INCLUDE_GENERATED_AT` defaults to `false` **on purpose**: omitting the timestamp is
what makes reports byte-reproducible.

## 10. Rule catalog

Every rule declares an evidence class and a default severity/confidence. The complete table
with false-positive notes and remediation guidance is in
[`docs/ANALYSIS_RULES.md`](docs/ANALYSIS_RULES.md); the machine-readable version is served by
`GET /api/v1/rules`.

| Rule | Title | Severity | Confidence | Class |
| --- | --- | --- | --- | --- |
| PY001 | Mutable default argument | medium | high | deterministic |
| PY002 | Bare except clause | medium | high | deterministic |
| PY003 | Exception swallowed without handling | medium | medium | deterministic |
| PY004 | `subprocess` execution with `shell=True` | high | medium | deterministic |
| PY005 | Dynamic code execution (`eval`/`exec`/`compile`) | high | high | deterministic |
| PY006 | Deserialisation of untrusted data | high | medium | deterministic |
| PY007 | Unsafe `yaml.load` | high | medium | deterministic |
| PY008 | `os.system` / `os.popen` | high | medium | deterministic |
| PY009 | `tempfile.mktemp` | medium | high | deterministic |
| PY010 | Weak hash algorithm | low | medium | deterministic |
| PY011 | TLS verification disabled | high | high | deterministic |
| PY012 | Unreachable statement after `return`/`raise` | low | medium | deterministic |
| PY013 | Blocking call without a timeout | low | low | heuristic |
| PY014 | Syntax error in an added file | high | high | deterministic |
| PY015 | `assert` used for runtime validation | low | medium | deterministic |
| SEC001 | Hard-coded credential | high | medium | deterministic |
| SEC002 | Private key material in source | critical | high | deterministic |
| SEC003 | High-entropy literal next to a secret-looking name | medium | low | heuristic |
| TST001 | Source changed without any test change | low | low | heuristic |
| TST002 | Changed line uncovered per the supplied report | low | medium | deterministic |
| TST003 | Coverage report does not mention a changed file | informational | medium | heuristic |

## 11. Sample report

`examples/sample_report.md` and `examples/sample_report.json` are produced by a real PRISM
run over the deliberate problems in [`samples/sample_project/`](samples/sample_project/).
That sample is **demonstration data**: the defects are planted on purpose and are not real
vulnerabilities in any third-party repository. `samples/sample_project/clean_module.py` is
the corrected counterpart and is asserted to produce **zero** findings.

## 12. Testing and quality checks

```bash
python -m pytest -q                                   # full suite
python -m pytest --cov=prism --cov-report=term-missing # with coverage
python -m pytest -m "not integration" -q              # skip opt-in network tests

ruff check prism tests
ruff format --check prism tests
bandit -r prism -ll
```

Design rules the suite enforces:

- Each analyzer rule has at least one positive, one negative and one boundary/malformed case.
- GitHub behaviour is tested through `httpx.MockTransport`. An autouse fixture makes the
  socket layer raise on any outbound connection, so a test that tried to reach the network
  would fail rather than silently pass.
- Regressions found during development are pinned by named tests (for example
  `test_a_removed_line_starting_with_dashes_is_not_mistaken_for_a_header`).
- Live tests exist but are skipped unless `PRISM_RUN_INTEGRATION=1`.

Details, including what each test file covers, are in [`docs/TESTING.md`](docs/TESTING.md).

## 13. Docker instructions

```bash
cp .env.example .env      # optional; never commit it
docker compose up --build
curl http://127.0.0.1:8000/health
```

The image runs as a non-root user (uid 10001), and the Compose service is hardened with a
read-only root filesystem, `no-new-privileges`, all capabilities dropped, a `noexec` tmpfs
for `/tmp`, and CPU/memory caps so a pathological diff cannot exhaust the host.

> **Environment note.** Docker was **not installed** in the environment where this project
> was built, so the container build could not be executed there. The Dockerfile and Compose
> file were validated statically and are built in CI (`.github/workflows/ci.yml`, `docker`
> job). See the completion report for the exact status wording.

## 14. Security and privacy notes

- **Analysed code is never executed.** No `eval`, no `exec`, no imports of reviewed modules,
  no running of repository scripts. A test asserts that a module whose import would abort the
  process is still analysed safely.
- **Repository content is untrusted data.** File paths, PR titles, commit messages and code
  comments are treated as text. Instructions embedded in them are not followed, and a test
  confirms that an "ignore all previous instructions" payload cannot suppress a finding.
- **SSRF is closed by construction.** PRISM talks only to allow-listed hosts
  (`api.github.com`, `github.com`) and the GitHub API endpoint accepts owner/repo/number —
  there is no field through which a caller can supply a URL to fetch.
- **Tokens.** Read from the environment only, sent only in the `Authorization` header, never
  logged, never included in a report, error body or evidence file. A logging filter redacts
  credential-shaped strings as a second layer.
- **Report injection.** Untrusted text is escaped, control characters stripped, HTML
  neutralised, and code fences grown to outgrow any backtick run in the content.
- **Resource limits.** Byte, file, page and response caps with typed errors, plus request-body
  and container limits.
- **No publishing.** PRISM never pushes, comments, or changes repository settings.

Full analysis, including residual risks, is in [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md)
and [`docs/DATA_PRIVACY.md`](docs/DATA_PRIVACY.md).

## 15. Limitations

Stated plainly, because a reviewer must know what a tool cannot see:

1. **Static analysis only.** PRISM cannot prove runtime behaviour. A finding describes what
   the diff contains.
2. **Changed lines only.** Pre-existing problems on unchanged lines are out of scope.
3. **Python analysis needs a parseable view.** A new file is parsed in full; a modified file
   is parsed from its added lines as a *fragment* (reported as such), and constructs that need
   unchanged surrounding context can be missed.
4. **Heuristics have false positives.** `PY013` and `SEC003` are correlation-based; `TST001`
   cannot know that tests already exist elsewhere.
5. **No coverage inference.** Without a Cobertura report PRISM makes no coverage statement,
   and it never derives a percentage from test-file counts.
6. **No severity mapping for external tools.** Ruff findings are imported at a fixed low
   severity, because mapping lint codes onto impact levels would be a guess.
7. **No LLM provider ships.** The extension point exists and is disabled by default; no
   evaluation of AI quality was performed, so none is claimed.
8. **No performance claims.** No benchmarks were run, so no numbers are quoted.

## 16. Roadmap

Candidate work, each depending on a real need:

- Additional languages (JavaScript/TypeScript, Go) behind the same rule registry.
- Per-repository rule configuration file (`.prism.toml`) instead of environment variables.
- Optional inline review comments — only with an explicit, least-privilege write path.
- A measured evaluation harness for the heuristic rules, so their false-positive rates can be
  reported as numbers rather than adjectives.
- SARIF output for native code-scanning integration.

## 17. Contribution guide

See [`CONTRIBUTING.md`](CONTRIBUTING.md). In short: inspect before you change, add a positive
and a negative test for every new rule, keep untrusted data out of executable paths, never
weaken a test to make CI green, and document any new limitation rather than hiding it.

---

## Projektzusammenfassung (Deutsch)

**PRISM — Intelligenter Pull-Request-Reviewer**

PRISM ist ein Python-Werkzeug, das Unified Diffs und GitHub-Pull-Requests automatisch
analysiert und nachvollziehbare Code-Review-Hinweise erzeugt. Jeder Befund enthält eine
stabile ID, eine Regel-ID, Schweregrad und Konfidenz, die genaue Datei- und Zeilenposition,
Codebelege, eine Risikoerklärung, einen konkreten Lösungsvorschlag und eine Testempfehlung.

**Technischer Aufbau.** Die Anwendung ist klar in Module getrennt (API, Core, Diff-Parser,
GitHub-Client, Analyzer, Engine, Findings, Reporting, Coverage). Die Regeln liegen in einer
Registry und lassen sich erweitern, ohne die Engine zu ändern. Die Python-Analyse basiert auf
dem Standardmodul `ast`; es kommen ausschließlich kostenlose, quelloffene Bibliotheken zum
Einsatz (FastAPI, Pydantic, httpx, pytest, Ruff, Bandit). Eine Datenbank wird bewusst nicht
verwendet.

**Sicherheit.** Analysierter Code wird niemals ausgeführt oder importiert. Repository-Inhalte
gelten als nicht vertrauenswürdige Daten. GitHub-Zugriffe erfolgen nur über eine feste
Positivliste von Hosts und ausschließlich lesend; Tokens stehen nur in Umgebungsvariablen und
werden in Logs und Berichten unkenntlich gemacht. Größen-, Datei- und Zeitlimits verhindern
Ressourcenüberlastung. Ein Bedrohungsmodell und ein Datenschutzkonzept sind dokumentiert.

**Qualitätssicherung.** Für jede Regel existieren Positiv-, Negativ- und Grenzfalltests;
GitHub-Aufrufe werden vollständig über Mock-Transporte getestet, sodass die Tests ohne
Netzwerk und ohne Zugangsdaten laufen. Zusätzlich werden Ruff (Linting) und Bandit
(Sicherheitsanalyse) sowie Coverage eingesetzt.

**Lernwert für die IT-Ausbildung.** Das Projekt verbindet Softwarearchitektur, statische
Analyse mit AST, REST-API-Design, Testautomatisierung, Containerisierung, CI/CD und
Security-Engineering — und dokumentiert bewusst auch Grenzen der Analyse.

---

## Licence

MIT — see [`LICENSE`](LICENSE). The licence choice is a documented assumption (`PLAN.md` §0);
verify it matches your intent before publishing.

<p align="right"><a href="#readme-top">↑ back to top</a></p>
