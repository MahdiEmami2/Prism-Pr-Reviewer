# Contributing to PRISM

Thanks for considering a contribution. PRISM's value comes from being *trustworthy*, so the
rules below are about honesty as much as about code style.

## 1. Before you change anything

1. Read `PLAN.md`, `docs/SPEC.md` and `docs/ARCHITECTURE.md`.
2. Inspect the workspace: Python version, installed tools, and the file you intend to touch.
3. Never delete or overwrite unrelated files, and never reformat a file you are not otherwise
   changing.
4. If a change would contradict the specification, update `docs/SPEC.md` in the same pull
   request and say so in the description.

## 2. Development setup

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
.\.venv\Scripts\Activate.ps1     # Windows PowerShell
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest -q
```

## 3. Adding a rule

Adding a rule must not require an engine change. Follow this checklist:

1. **Declare a `RuleSpec`** in the relevant analyzer module with a stable ID, a title, a
   category, a default severity, a default confidence, the evidence class, a risk
   description, a remediation, an optional test recommendation, and
   `documentation="docs/ANALYSIS_RULES.md"`.
   - Number Python rules `PYnnn`, secret rules `SECnnn`, testing rules `TSTnnn`.
   - IDs are permanent. Do not renumber an existing rule; deprecate it instead.
2. **Choose the evidence class honestly.** `deterministic` only if the conclusion follows from
   the changed lines alone. If the finding depends on context the diff cannot contain, it is
   `heuristic` and its confidence is at most `medium` — usually `low`.
3. **Never inflate severity.** Severity means impact if the code ships as-is. A pattern that
   *might* be a vulnerability is `medium`, not `critical`.
4. **Anchor the line correctly.** Use `factory.line_if_changed(...)`; never invent a line
   number. If the location is genuinely file-level, pass `line=None` and say so in the message.
5. **Write the tests.** A new rule needs, at minimum:
   - one positive case asserting the rule ID (and the confidence where it matters),
   - one negative case using the compliant variant of the same code,
   - one boundary or malformed-input case,
   - a regression test if the rule fixes a bug,
   - and, where feasible, a false-positive-resistance case.
6. **Document it** in `docs/ANALYSIS_RULES.md` with a table row and a false-positives note.
7. **Update the traceability matrix** if the rule implements a numbered requirement.

## 4. Never do these

- **Do not weaken or delete a test to make CI green.** Fix the root cause. If a test is
  genuinely wrong, fix the test *and* explain why in the pull request.
- **Do not execute analysed code**, import it, or run repository scripts during a review.
- **Do not `eval`, `exec`, or build a shell string** from any value that came from a diff, a
  path, a branch name or a PR field.
- **Do not accept a URL from a caller.** Add the host to the allow-list in
  `prism/github/urls.py` and construct the URL there, or don't add the feature.
- **Do not log, report or commit a token, a private key, or an environment dump.**
- **Do not add a paid API, a commercial LLM or a cloud service to the core path.** Core
  analysis must work offline and without a key.
- **Do not add a database** without demonstrating a requirement that cannot be met otherwise.
- **Do not claim a capability you did not verify.** No performance numbers, no accuracy
  percentages, no certifications, no "production-ready" claims without evidence.

## 5. Code style

- Ruff configuration lives in `pyproject.toml`; line length is 100.
- Type annotations on public functions. `from __future__ import annotations` is used
  throughout.
- Docstrings explain *why* a decision was made, not what the next line does.
- Errors are typed `PrismError` subclasses with a stable `code` and an `http_status`; never
  raise a bare `Exception` for a domain condition.
- Keep module boundaries as described in `docs/ARCHITECTURE.md`. `core` must not import
  `api`, and no module below the API layer may import it.

## 6. Pull request checklist

- [ ] `python -m pytest -q` passes.
- [ ] `ruff check prism tests` passes.
- [ ] `ruff format --check prism tests` passes.
- [ ] `bandit -r prism -ll` reports nothing new, or the finding is explained in the description.
- [ ] New behaviour is covered by tests that would fail without the change.
- [ ] Documentation and the rule catalogue are updated.
- [ ] No secret, token, private key or environment dump is included.
- [ ] The description states what was **not** done or could not be verified.

## 7. Reporting a bug

Include: PRISM version (`python -m prism version`), Python version, the exact command, the
relevant input (redacted), the observed behaviour, and the expected behaviour. Never paste a
real token or private source code — redact it first.

## 8. Reporting a security issue

Please follow `SECURITY.md` rather than opening a public issue.

## 9. Licence

Contributions are accepted under the MIT licence (see `LICENSE`). By opening a pull request you
confirm you have the right to submit the work under those terms.
