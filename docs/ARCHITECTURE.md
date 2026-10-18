# Architecture

## 1. Design goals

1. **Deterministic first.** Every claim must follow from the diff. Anything that merely
   correlates is labelled heuristic and carries lower confidence.
2. **One untrusted-input boundary.** Repository content enters the system as text, is parsed
   as data, and is never given to an interpreter, an importer or a shell.
3. **Honest scope.** What was skipped, why, and which limits were reached is part of the
   output contract, not a log line.
4. **Extensibility without engine edits.** Adding a rule means adding a class and one registry
   entry.

## 2. Module map

| Module | Responsibility | Must not do |
| --- | --- | --- |
| `prism/core` | Configuration, shared enums, typed errors, limits, redaction, logging | Know about analyzers or reporting |
| `prism/diff` | Parse unified diffs; map changed lines; reconstruct a full new file when the patch contains it | Interpret the meaning of any line |
| `prism/github` | Allow-listed URL construction, read-only REST client, patch → diff conversion | Write to GitHub; accept an arbitrary URL |
| `prism/analyzers` | The rule registry plus independent rule implementations | Orchestrate a whole review; read files from disk |
| `prism/engine` | Build one `AnalysisContext` per file, run the registry, assemble the scope report | Contain rule logic |
| `prism/findings` | Finding model, stable identity, deduplication, policy filtering | Render output |
| `prism/coverage` | Cobertura XML reading with line-explicit matching | Infer coverage from file counts |
| `prism/reporting` | Markdown and JSON rendering, sanitisation | Compute findings |
| `prism/api` | FastAPI schemas, routes, error envelope, body-size middleware | Contain analysis logic |

Dependency direction is one-way: `api → engine → analyzers → (diff, core, findings)`. No
module imports `api`, and `core` imports nothing from the project.

## 3. Data flow

```
                     ┌────────────────────────┐
  diff file / stdin ─┤                        │
                     │  parse_unified_diff    ├─► ParsedDiff(files, skipped, diagnostics)
  git repo ──────────┤  parse_local_git_diff  │
                     └────────────────────────┘
  GitHub PR ──► GitHubClient ──► files_from_github ──► ParsedDiff
                                   │
                                   ▼
                    analyze_parsed_diff(parsed, config, registry)
                                   │
      per file: AnalysisContext(file, added_lines, full_source | fragment)
                                   │
                    for analyzer in registry.analyzers(): analyzer.analyze(ctx)
                                   │
                review-level: test awareness; coverage findings
                                   │
                             deduplicate()      ← stable finding IDs
                                   │
                             apply_policy()     ← min severity, exclusions, overrides
                                   │
                              ReviewResult
                        ┌──────────┴──────────┐
                        ▼                     ▼
                 render_markdown()      render_json()
```

## 4. The untrusted-input boundary

Everything crossing into PRISM from outside is treated as data with no authority:

| Input | How it is handled |
| --- | --- |
| Diff text | Parsed line by line with no interpretation; never written to disk; never executed |
| File paths from the diff | Normalised for the finding identity; `..` segments are collapsed; no path is ever opened |
| Python source | `ast.parse` only. The module is never imported, compiled or run |
| YAML/settings files | Scanned as text by line rules; never parsed by PRISM |
| PR title, body, author, branch | Sanitised before rendering; cannot restructure a report |
| Code comments | Text. An instruction embedded in a comment is not an instruction to PRISM |
| Coverage XML | Size-capped, parsed with entity expansion disabled, values never used as paths |
| GitHub responses | Size-capped, JSON-parsed, mapped onto typed errors |

### Why a complete-source requirement exists

`ast.parse` on a fragment would succeed on some inputs while describing code that does not
exist. PRISM therefore distinguishes three views and records which one was used:

| View | When | Consequence |
| --- | --- | --- |
| `complete` | The diff adds a whole new file | Full module analysis; a syntax error is a definite fact about the author's code |
| `fragment` | A modified file with parseable added lines | Analysis of the added block only; a parse failure is a *scope limitation*, not a defect; reported in `scope.diagnostics` |
| `none` | No parseable added lines (for example removals only) | No AST analysis; recorded as `no_analyzable_source_view` |

## 5. Rule system

```python
class Analyzer(Protocol):
    name: str
    def rule_specs(self) -> Sequence[RuleSpec]: ...
    def analyze(self, context: AnalysisContext) -> Iterable[Finding]: ...
```

`RuleSpec` carries the rule metadata (ID, title, category, default severity, default
confidence, evidence class, description, remediation, test recommendation, documentation
anchor). `RuleRegistry` refuses duplicate analyzer names and duplicate rule IDs, so a
collision is a startup error rather than a silently shadowed rule.

`FindingFactory.create()` derives the finding ID from `(rule_id, normalized path, symbol,
normalized signature, discriminator)`. `line` is passed through `line_if_changed()`, which
returns `None` unless the line is genuinely part of the diff — a rule cannot accidentally
anchor a finding to an unchanged line.

**Out-of-scope filtering.** A deterministic rule whose match lands on an unchanged line is
dropped, because a pull-request review comments on the change, not on pre-existing code.

## 6. Finding identity and deduplication

```
finding_id = "<rule_id>-" + sha256("<rule>|<path>|<symbol>|<signature>|<discriminator>")[:16]
```

Line numbers are deliberately absent, so inserting code above a finding does not change its
identity. `normalize_signature` strips comments, string-literal bodies and whitespace so a
reflowed line keeps its identity while a genuinely different statement does not.

Deduplication groups by ID, keeps the item with the shortest evidence tuple (ties broken by
rule ID for stability) and returns a merge log, so a collapse is auditable.

## 7. Reporting contract

The Markdown report always contains the same ten sections in the same order, including when
there are no findings. The JSON document has a fixed key order and omits `generated_at`
unless explicitly enabled, which is what makes byte-identical output possible.

Both formats are generated from one source — `ReviewResult.to_dict()` — so the API response
and the JSON report cannot drift apart.

## 8. Error model

`PrismError` subclasses carry a stable `code` and an HTTP status. The API maps them onto one
envelope; the CLI prints `code`, message and details to stderr and exits non-zero. Unhandled
exceptions produce a generic body: no traceback, no filesystem path, no environment value.

## 9. Deliberate non-choices

| Not used | Reason |
| --- | --- |
| Database (SQLite/PostgreSQL) | The analysis is stateless. Persisting untrusted repository content would add risk without a requirement |
| Frontend framework | The deliverable is a CLI and an API |
| Message broker / microservices | No concurrency requirement justifies the operational cost |
| LLM provider | The requirement allows an extension point, not a dependency. Shipping none keeps the "no API key needed" guarantee true |
| Caching of GitHub responses | Would persist third-party content beyond the review |
