# Analysis rules

Every rule below is implemented and tested. `severity` describes potential impact;
`confidence` describes how strongly the diff evidence supports the finding. The two are
independent — a certain pattern with low impact keeps `high` confidence.

**Evidence class.** `deterministic` means the construct is unambiguously present in the
changed lines and the conclusion follows from the diff. `heuristic` means the diff shows only
a pattern that correlates with a problem; the finding is a review prompt and is expected to
have false positives.

**Out-of-scope rule.** A deterministic rule that matches a line which is *not* part of the
diff is discarded: a pull-request review comments on the change, not on pre-existing code.

---

## Python AST rules (`prism/analyzers/python_rules.py`)

### PY001 — Mutable default argument
| | |
| --- | --- |
| Severity / confidence | medium / high |
| Evidence class | deterministic |
| Fires on | A `def` parameter whose default is a list, dict or set literal |
| Silent on | `items=None` built inside the body; `list()`/`dict()`/`set()` calls (fresh per call) |
| Why it matters | The default object is created once at definition time and shared by every call, so mutating it leaks state between calls. This is documented language behaviour, not a style opinion. |
| Fix | Use `None` as the default and construct the container in the body. |
| Test | Call the function twice and assert the second call is unaffected. |

### PY002 — Bare except clause
| | |
| --- | --- |
| Severity / confidence | medium / high |
| Evidence class | deterministic |
| Fires on | `except:` with no exception type |
| Silent on | `except ValueError:` and any typed clause |
| Why it matters | A bare `except` catches `BaseException`, which includes `KeyboardInterrupt` and `SystemExit`, changing process behaviour on interrupt. |
| Fix | Catch the specific exception type, or at least `except Exception`. |

### PY003 — Exception swallowed without handling
| | |
| --- | --- |
| Severity / confidence | medium / medium |
| Evidence class | deterministic |
| Fires on | An `except` block whose entire body is `pass` |
| Silent on | A body that logs, raises, or does anything else |
| Why it matters | The construct is definitely present; whether discarding the error is wrong depends on intent the diff cannot show, hence medium confidence. |
| Fix | Log the exception, re-raise it, or narrow the `try` block. |
| Test | Provoke the exception and assert the outcome. |

### PY004 — `subprocess` with `shell=True`
| | |
| --- | --- |
| Severity / confidence | high / medium |
| Evidence class | deterministic |
| Fires on | `subprocess.run/call/check_call/check_output/Popen` with a literal `shell=True` |
| Silent on | `shell=False`, and calls with no `shell` keyword |
| Why it matters | A shell interprets every interpolated value as shell syntax, so data becomes a command. The call is definitely shell-based; exploitability depends on where the arguments come from, which the diff may not show. |
| Fix | Pass an argv list with `shell=False`; if a shell is unavoidable, quote every interpolated value with `shlex.quote`. |

### PY005 — Dynamic code execution
| | |
| --- | --- |
| Severity / confidence | high / high |
| Evidence class | deterministic |
| Fires on | `eval(...)`, `exec(...)`, builtin `compile(...)` |
| Silent on | `ast.literal_eval(...)`, `re.compile(...)` |
| Why it matters | These turn data into code. The construct is unambiguously present in the changed lines. |
| Fix | Replace with a parser, a mapping of allowed operations, or an explicit evaluator. |

### PY006 — Deserialisation of untrusted data
| | |
| --- | --- |
| Severity / confidence | high / medium |
| Evidence class | deterministic |
| Fires on | `pickle.load/loads`, `pickle.Unpickler`, `dill.load/loads`, `marshal.load/loads`, `jsonpickle.decode`, `shelve.open` |
| Silent on | `json.loads`, `yaml.safe_load` |
| Why it matters | These formats can execute code while loading. The call is present; whether the payload is trusted cannot be decided from the diff. |
| Fix | Use a data-only format such as JSON. |

### PY007 — Unsafe `yaml.load`
| | |
| --- | --- |
| Severity / confidence | high / medium |
| Evidence class | deterministic |
| Fires on | `yaml.load(...)` without a `Loader`, or with a non-`Safe` loader |
| Silent on | `yaml.safe_load(...)`, `yaml.load(..., Loader=yaml.SafeLoader)` |
| Why it matters | The default loader constructs arbitrary Python objects from the document. |
| Fix | Use `yaml.safe_load`, or pass `Loader=yaml.SafeLoader`. |

### PY008 — `os.system` / `os.popen`
| | |
| --- | --- |
| Severity / confidence | high / medium |
| Evidence class | deterministic |
| Fires on | `os.system(...)`, `os.popen(...)` |
| Silent on | `subprocess.run([...])` with an argv list |
| Why it matters | Both always involve a shell, so interpolated values become shell syntax, and neither can report an exit status safely. |
| Fix | Use `subprocess.run` with an argv list and `shell=False`. |

### PY009 — `tempfile.mktemp`
| | |
| --- | --- |
| Severity / confidence | medium / high |
| Evidence class | deterministic |
| Fires on | `tempfile.mktemp(...)` |
| Silent on | `NamedTemporaryFile`, `mkstemp`, `TemporaryDirectory` |
| Why it matters | `mktemp` returns a *name* without creating the file, so another process can claim it first — a documented TOCTOU hazard the standard library marks as deprecated. |
| Fix | Use `tempfile.NamedTemporaryFile` or `tempfile.mkstemp`. |

### PY010 — Weak hash algorithm
| | |
| --- | --- |
| Severity / confidence | low / medium |
| Evidence class | deterministic |
| Fires on | `hashlib.md5(...)`, `hashlib.sha1(...)` without `usedforsecurity=...` |
| Silent on | `hashlib.sha256(...)`; an explicit `usedforsecurity=False` |
| Why it matters | MD5 and SHA-1 are collision-broken for security purposes. They remain legitimate for non-security checksums, which the diff cannot distinguish — hence low severity. |
| Fix | Use SHA-256 for security, or pass `usedforsecurity=False` to record that the hash is not a security control. |

### PY011 — TLS verification disabled
| | |
| --- | --- |
| Severity / confidence | high / high |
| Evidence class | deterministic |
| Fires on | `requests`/`httpx`/`aiohttp`/`urllib3` calls with a literal `verify=False` |
| Silent on | `verify=True` or an unset `verify` |
| Why it matters | Certificate validation is disabled for the whole request, so any network attacker can impersonate the peer. |
| Fix | Remove `verify=False` and install the missing CA bundle instead. |

### PY012 — Unreachable statement after `return`/`raise`
| | |
| --- | --- |
| Severity / confidence | low / medium |
| Evidence class | deterministic |
| Fires on | A statement inside the same block directly after `return`, `raise`, `continue` or `break` — except a lone `pass` or a docstring, which are not reported |
| Silent on | Branches that each terminate the block (for example `if/else` returning in both arms) |
| Why it matters | Reachability inside a single block is decided locally, so the statement is definitely dead. Its intent is unknown, hence low severity. |
| Fix | Delete the dead statement or move it before the terminating statement. |

### PY013 — Blocking call without a timeout
| | |
| --- | --- |
| Severity / confidence | low / **low** |
| Evidence class | **heuristic** |
| Fires on | `subprocess.run/call/check_call/check_output` without a `timeout`; `requests`/`httpx`/`aiohttp`/`urllib3` requests without a `timeout` |
| Silent on | An explicit `timeout=...` |
| Why it matters | A call with no timeout can block indefinitely. Absence of the keyword is *weak* evidence: a timeout may come from a shared session, a wrapper or a decorator that the diff does not contain. This rule is expected to have false positives. |
| Fix | Pass an explicit timeout, or set one on the shared client/session. |

### PY014 — Syntax error in an added file
| | |
| --- | --- |
| Severity / confidence | high / high |
| Evidence class | deterministic |
| Fires on | A **newly added** file whose complete content does not parse |
| Silent on | A valid file. A *modified* file that does not parse is reported as a scope limitation, not as a finding |
| Why it matters | The added file does not parse. That is a definite language-level fact about the file content. |
| Fix | Fix the syntax error reported by the parser. |

### PY015 — `assert` used for runtime validation
| | |
| --- | --- |
| Severity / confidence | low / medium |
| Evidence class | deterministic |
| Fires on | Any `assert` statement |
| Silent on | Explicit `raise` statements |
| Why it matters | Assertions are removed under `python -O`, so validation performed only with `assert` disappears in optimised mode. |
| Fix | Raise an explicit exception for input validation. |

---

## Secret rules (`prism/analyzers/secrets.py`)

These run on added lines of **any** text file, because a credential in a YAML or `.properties`
file matters as much as one in Python.

### SEC001 — Hard-coded credential
| | |
| --- | --- |
| Severity / confidence | high / medium |
| Evidence class | deterministic |
| Fires on | A string literal assigned to a credential-shaped name (`password`, `secret`, `api_key`, `access_key`, `private_key`, `auth_token`, `client_secret`, `token`, `credential`, `connection_string`, and prefixed/suffixed variants), matching both `key = "value"` and `key: "value"` |
| Silent on | Environment lookups (`os.environ`, `os.getenv`, `config.get`, `settings.`, `vault`, `secretmanager`); values shorter than 8 characters; values with two or fewer distinct characters; obvious placeholders (see below); sequential runs (`abcdefghij`, `1234567890`) |
| Why it matters | The assignment is present in the diff. Whether the value is a real secret or a throwaway value cannot be proven from the diff, hence medium confidence. |
| Reporting behaviour | The matched value is **masked** (first four and last four characters) in both the message and the evidence. |
| Fix | Read the value from the environment or a secret manager, and rotate the exposed credential if it was ever committed. |

**Placeholder safeguards** (implemented in `is_placeholder`, unit-tested as a first-class
behaviour):

| Guard | Examples that are silenced |
| --- | --- |
| Literal placeholder words | `changeme`, `CHANGE_ME`, `placeholder`, `replace_me`, `redacted` |
| Example/dummy/fake/test prefixes | `example_token`, `dummy_value`, `test-secret` |
| Possessive prefixes | `your_api_key_here` |
| Directive words | `TODO`, `FIXME`, `TBD`, `goes_here` |
| Angle brackets and braces | `<inject-at-deploy-time>`, `${SECRET_VALUE}` |
| Environment interpolation | `${VAR}`, `%s`, `os.environ[...]` |
| Low-entropy runs | `xxxxxxxx`, `0000000000`, `abcdefghij`, `9876543210` |
| Null-ish words | `none`, `null`, `empty`, `unset`, `not_set` |
| Short or degenerate values | under 8 characters, or fewer than 3 distinct characters |

### SEC002 — Private key material in source
| | |
| --- | --- |
| Severity / confidence | **critical** / high |
| Evidence class | deterministic |
| Fires on | A PEM private-key header (`-----BEGIN … PRIVATE KEY-----`) in an added line |
| Silent on | `BEGIN PUBLIC KEY`, `BEGIN CERTIFICATE` |
| Why it matters | Key material in a source tree is readable by everyone with repository access. The header itself is unambiguous evidence — this is the only rule that reports `critical`. |
| Fix | Remove the key, rotate it, and load it from a secret store at runtime. |

### SEC003 — High-entropy literal next to a secret-looking name
| | |
| --- | --- |
| Severity / confidence | medium / **low** |
| Evidence class | **heuristic** |
| Fires on | A quoted token of ≥24 characters matching `[A-Za-z0-9+/=_-]+` with Shannon entropy ≥ 3.5, on a line that also contains a secret-like word and that SEC001 did **not** already report |
| Silent on | Text containing spaces; short values; low-entropy values |
| Why it matters | Entropy is a correlation, not proof. Build hashes, base64 fixtures and sample data look identical, so this is a review prompt only. |
| Fix | Confirm whether the value is a real credential; if so, move it to a secret store. |

---

## Testing rules (`prism/analyzers/test_awareness.py`)

### TST001 — Source changed without any test change
| | |
| --- | --- |
| Severity / confidence | low / **low** |
| Evidence class | **heuristic** |
| Fires on | A review that changes source files while changing **no** file matching the configured test conventions. One aggregate finding, listing up to 20 changed source paths |
| Silent on | Any review that touches a test file; a review that changes only tests |
| Location | Review-level: `path = "<review>"`, `line = null` |
| Why it matters | This is a review prompt, not proof. Tests may already cover the behaviour, the convention may not match this repository, or the change may not need tests (docs, CI, configuration). |
| Fix | Confirm existing coverage, or add the missing test in this pull request. |

Default conventions (`PRISM`-configurable): `tests/test_*.py`, `tests/**/test_*.py`,
`test_*.py`, `*_test.py`, `conftest.py`, `**/conftest.py`. A glob may match the full path or
just the basename.

### TST002 — Changed line uncovered per the supplied report
| | |
| --- | --- |
| Severity / confidence | low / medium |
| Evidence class | deterministic |
| Fires on | A changed line that the supplied Cobertura report explicitly lists with zero hits. At most 20 per file |
| Silent on | Lines the report does not list; any run without a coverage report |
| Why it matters | The report explicitly covers the line, which is stronger than inferring anything from the presence of test files. |
| Fix | Add a test that executes this line, or confirm the line is unreachable. |

### TST003 — Coverage report does not mention a changed file
| | |
| --- | --- |
| Severity / confidence | informational / medium |
| Evidence class | **heuristic** |
| Fires on | A changed file with no entry in the supplied report |
| Why it matters | Usually an outdated report or a module the test suite never imports. **No percentage is claimed for this file.** |
| Fix | Regenerate the coverage report for this revision before drawing conclusions. |

---

## Optional external tools (`prism/analyzers/external.py`)

Disabled by default (`PRISM_ENABLE_EXTERNAL_TOOLS=true` to enable). Availability is checked
first; the return code is always inspected.

| Rule | Source | Severity | Notes |
| --- | --- | --- | --- |
| `EXT-RUFF` | `ruff check --output-format json` | low (fixed) | PRISM does **not** map Ruff codes onto impact levels; doing so would be a guess |
| `EXT-BANDIT` | `bandit -f json` | mechanical mapping of Bandit's own LOW/MEDIUM/HIGH | PRISM does not elevate it further |

Failure handling: executable missing → `unavailable`; timeout → `timeout`; exit code other than
0/1 → `failed` with the code and stderr tail; unparseable output → `failed`. A tool failure is
never silently ignored and never reported as zero findings.

## Optional LLM extension (`prism/analyzers/llm_extension.py`)

An interface plus a `NullProvider`. **No provider is implemented**, so no API key exists or is
needed. If one were added, the documented contract requires: disabled by default; output
validated against a strict schema; every model-supplied path and line re-checked against the
actual diff and discarded when it does not match; every model finding labelled `heuristic`
with low confidence; and `merge_llm_findings` unions rather than replaces, so an LLM can
**never** remove a deterministic finding. No claim about AI accuracy is made, because none was
measured.
