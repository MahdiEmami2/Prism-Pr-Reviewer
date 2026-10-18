"""Deterministic Python analysis rules based on the standard-library ``ast`` module.

Safety model (unchanged for every rule in this module):

* Source is parsed with :func:`ast.parse` in memory. It is never imported, compiled,
  executed, or written to disk.
* Only files whose complete new content is present in the diff are AST-analysed. For a
  partial patch the module emits a scope diagnostic instead of a finding, because parsing
  a fragment would produce line numbers and conclusions that do not correspond to real
  code.
* A syntax error in a *newly added* file is a definite language-level fact and is reported
  as such. For other files a parse failure is reported as "could not analyse", not as a
  defect in the author's code.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Sequence

from prism.analyzers.base import AnalysisContext, FindingFactory, RuleSpec
from prism.core.types import Confidence, FindingClass, Severity
from prism.findings.models import Finding

CATEGORY_SECURITY = "security"
CATEGORY_RELIABILITY = "reliability"
CATEGORY_CORRECTNESS = "correctness"
CATEGORY_MAINTAINABILITY = "maintainability"

_DOC = "docs/ANALYSIS_RULES.md"

SPECS: dict[str, RuleSpec] = {
    "PY001": RuleSpec(
        rule_id="PY001",
        title="Mutable default argument",
        category=CATEGORY_CORRECTNESS,
        default_severity=Severity.MEDIUM,
        default_confidence=Confidence.HIGH,
        finding_class=FindingClass.DETERMINISTIC,
        description=(
            "A default value that is a list, dict, or set literal is created once at "
            "function definition time and shared across every call. Mutating it inside the "
            "function leaks state between calls, which is a documented language behaviour, "
            "not a style preference."
        ),
        remediation="Use None as the default and build the container inside the body.",
        test_recommendation="Call the function twice and assert the second call is unaffected.",
        documentation=_DOC,
    ),
    "PY002": RuleSpec(
        rule_id="PY002",
        title="Bare except clause",
        category=CATEGORY_RELIABILITY,
        default_severity=Severity.MEDIUM,
        default_confidence=Confidence.HIGH,
        finding_class=FindingClass.DETERMINISTIC,
        description=(
            "A bare 'except:' catches BaseException, including KeyboardInterrupt and "
            "SystemExit. This changes process behaviour on interrupt, which the diff alone "
            "proves."
        ),
        remediation="Catch the specific exception type, or at least 'except Exception'.",
        documentation=_DOC,
    ),
    "PY003": RuleSpec(
        rule_id="PY003",
        title="Exception swallowed without handling",
        category=CATEGORY_RELIABILITY,
        default_severity=Severity.MEDIUM,
        default_confidence=Confidence.MEDIUM,
        finding_class=FindingClass.DETERMINISTIC,
        description=(
            "An except block whose body is only 'pass' discards the error. The construct is "
            "definitely present; whether discarding it is wrong depends on intent that the "
            "diff cannot show, hence medium confidence."
        ),
        remediation="Log the exception, re-raise it, or narrow the try block.",
        test_recommendation="Add a test that provokes the exception and asserts the outcome.",
        documentation=_DOC,
    ),
    "PY004": RuleSpec(
        rule_id="PY004",
        title="subprocess execution with shell=True",
        category=CATEGORY_SECURITY,
        default_severity=Severity.HIGH,
        default_confidence=Confidence.MEDIUM,
        finding_class=FindingClass.DETERMINISTIC,
        description=(
            "shell=True routes the command through the platform shell, so any interpolated "
            "value becomes shell syntax. The call is definitely shell-based; exploitability "
            "depends on where the arguments come from, which the diff may not show."
        ),
        remediation=(
            "Pass an argument list with shell=False, or use shlex.quote for every "
            "interpolated value if a shell is unavoidable."
        ),
        documentation=_DOC,
    ),
    "PY005": RuleSpec(
        rule_id="PY005",
        title="Dynamic code execution",
        category=CATEGORY_SECURITY,
        default_severity=Severity.HIGH,
        default_confidence=Confidence.HIGH,
        finding_class=FindingClass.DETERMINISTIC,
        description=(
            "eval, exec and compile turn data into code. The construct is unambiguously "
            "present in the changed lines and is a recognised code-execution sink."
        ),
        remediation="Replace with a parser or an explicit mapping of allowed operations.",
        documentation=_DOC,
    ),
    "PY006": RuleSpec(
        rule_id="PY006",
        title="Deserialisation of untrusted data",
        category=CATEGORY_SECURITY,
        default_severity=Severity.HIGH,
        default_confidence=Confidence.MEDIUM,
        finding_class=FindingClass.DETERMINISTIC,
        description=(
            "pickle, dill and marshal can execute code while loading. The call is present; "
            "whether the payload is trusted cannot be decided from the diff."
        ),
        remediation=(
            "Use a data-only format such as JSON, or restrict unpickling to an allow-listed "
            "Unpickler."
        ),
        documentation=_DOC,
    ),
    "PY007": RuleSpec(
        rule_id="PY007",
        title="Unsafe YAML load",
        category=CATEGORY_SECURITY,
        default_severity=Severity.HIGH,
        default_confidence=Confidence.MEDIUM,
        finding_class=FindingClass.DETERMINISTIC,
        description=(
            "yaml.load without SafeLoader constructs arbitrary Python objects. The unsafe "
            "call is present; the trust level of the document is outside the diff."
        ),
        remediation="Use yaml.safe_load, or pass Loader=yaml.SafeLoader.",
        documentation=_DOC,
    ),
    "PY008": RuleSpec(
        rule_id="PY008",
        title="Shell command through os.system / os.popen",
        category=CATEGORY_SECURITY,
        default_severity=Severity.HIGH,
        default_confidence=Confidence.MEDIUM,
        finding_class=FindingClass.DETERMINISTIC,
        description=(
            "os.system and os.popen always involve a shell, so interpolated values are "
            "executed as shell syntax."
        ),
        remediation="Use subprocess.run with an argument list and shell=False.",
        documentation=_DOC,
    ),
    "PY009": RuleSpec(
        rule_id="PY009",
        title="Insecure temporary file creation",
        category=CATEGORY_SECURITY,
        default_severity=Severity.MEDIUM,
        default_confidence=Confidence.HIGH,
        finding_class=FindingClass.DETERMINISTIC,
        description=(
            "tempfile.mktemp returns a name without creating the file, so another process "
            "can claim it first. The standard library documents it as deprecated for this "
            "reason."
        ),
        remediation="Use tempfile.NamedTemporaryFile or tempfile.mkstemp.",
        documentation=_DOC,
    ),
    "PY010": RuleSpec(
        rule_id="PY010",
        title="Weak hash algorithm",
        category=CATEGORY_SECURITY,
        default_severity=Severity.LOW,
        default_confidence=Confidence.MEDIUM,
        finding_class=FindingClass.DETERMINISTIC,
        description=(
            "MD5 and SHA-1 are collision-broken for security purposes. They remain "
            "legitimate for non-security checksums, which the diff cannot distinguish."
        ),
        remediation=(
            "Use sha256 for security purposes, or pass usedforsecurity=False to record that "
            "the hash is not a security control."
        ),
        documentation=_DOC,
    ),
    "PY011": RuleSpec(
        rule_id="PY011",
        title="TLS verification disabled",
        category=CATEGORY_SECURITY,
        default_severity=Severity.HIGH,
        default_confidence=Confidence.HIGH,
        finding_class=FindingClass.DETERMINISTIC,
        description="verify=False disables certificate validation for the whole request.",
        remediation="Remove verify=False; install the missing CA bundle instead.",
        documentation=_DOC,
    ),
    "PY012": RuleSpec(
        rule_id="PY012",
        title="Unreachable statement after return or raise",
        category=CATEGORY_CORRECTNESS,
        default_severity=Severity.LOW,
        default_confidence=Confidence.MEDIUM,
        finding_class=FindingClass.DETERMINISTIC,
        description=(
            "A statement placed in the same block directly after a return, raise, continue "
            "or break can never run. Reachability inside one block is decided locally, so "
            "the statement is definitely dead; only its intent is unknown."
        ),
        remediation="Delete the dead statement or move it before the terminating statement.",
        documentation=_DOC,
    ),
    "PY013": RuleSpec(
        rule_id="PY013",
        title="Blocking call without a timeout",
        category=CATEGORY_RELIABILITY,
        default_severity=Severity.LOW,
        default_confidence=Confidence.LOW,
        finding_class=FindingClass.HEURISTIC,
        description=(
            "A network or subprocess call with no timeout can block indefinitely. Absence of "
            "a keyword argument is weak evidence: a timeout may be supplied through a shared "
            "session, a wrapper or a decorator that the diff does not contain."
        ),
        remediation="Pass an explicit timeout, or set one on the shared client/session.",
        test_recommendation="Add a test that asserts the call fails fast when the peer stalls.",
        documentation=_DOC,
    ),
    "PY014": RuleSpec(
        rule_id="PY014",
        title="Syntax error in an added file",
        category=CATEGORY_CORRECTNESS,
        default_severity=Severity.HIGH,
        default_confidence=Confidence.HIGH,
        finding_class=FindingClass.DETERMINISTIC,
        description=(
            "The added file does not parse as Python. This is a definite language-level fact "
            "about the file content, not a heuristic."
        ),
        remediation="Fix the syntax error reported by the parser.",
        documentation=_DOC,
    ),
    "PY015": RuleSpec(
        rule_id="PY015",
        title="Assertion used for runtime validation",
        category=CATEGORY_RELIABILITY,
        default_severity=Severity.LOW,
        default_confidence=Confidence.MEDIUM,
        finding_class=FindingClass.DETERMINISTIC,
        description=(
            "Assertions are removed when Python runs with -O, so a validation performed only "
            "with assert disappears in optimised mode."
        ),
        remediation="Raise an explicit exception for input validation.",
        documentation=_DOC,
    ),
}


def _dotted_name(node: ast.AST) -> str:
    """Return the dotted name of a Name/Attribute chain, else an empty string."""
    parts: list[str] = []
    current: ast.AST | None = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _call_keyword(call: ast.Call, name: str) -> ast.keyword | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword
    return None


def _is_true_literal(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _is_false_literal(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _mutable_default(node: ast.AST) -> bool:
    if isinstance(node, (ast.List, ast.Dict, ast.Set)):
        return True
    if isinstance(node, ast.ListComp):
        return False
    # list() / dict() / set() calls are freshly built on each call, so they are safe.
    return False


def _symbol_for_lineno(tree: ast.AST, lineno: int) -> str | None:
    """Best-effort qualified name of the innermost function/class containing a line."""
    best: str | None = None
    best_span = None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        end = getattr(node, "end_lineno", None)
        if end is None:
            continue
        if node.lineno <= lineno <= end:
            span = end - node.lineno
            if best_span is None or span <= best_span:
                best = node.name
                best_span = span
    return best


class _Collector:
    """Walks a parsed module and records raw rule matches."""

    def __init__(self, tree: ast.Module) -> None:
        self.tree = tree
        self.matches: list[tuple[str, int, str, str]] = []
        # (rule_id, lineno, signature, note)

    def add(self, rule_id: str, node: ast.AST, signature: str, note: str = "") -> None:
        lineno = getattr(node, "lineno", 0) or 0
        self.matches.append((rule_id, lineno, signature, note))

    # ------------------------------------------------------------------ rules

    def walk(self) -> None:
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._function(node)
            elif isinstance(node, ast.ExceptHandler):
                self._except(node)
            elif isinstance(node, ast.Call):
                self._call(node)
            elif isinstance(node, ast.Assert):
                self.add("PY015", node, ast.dump(node.test, annotate_fields=False)[:160])
        for node in ast.walk(self.tree):
            if isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                    ast.Module,
                    ast.ClassDef,
                    ast.If,
                    ast.For,
                    ast.While,
                    ast.With,
                    ast.Try,
                    ast.AsyncWith,
                    ast.AsyncFor,
                ),
            ):
                self._unreachable(node)

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        # `defaults` covers positional defaults; keyword-only defaults live in
        # `kw_defaults` and are aligned with `kwonlyargs` (an entry may be None).
        defaults = list(node.args.defaults)
        defaults.extend(default for default in node.args.kw_defaults if default is not None)
        for default in defaults:
            if _mutable_default(default):
                self.add(
                    "PY001",
                    default,
                    f"{node.name}:{type(default).__name__}",
                    node.name,
                )

    def _except(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self.add("PY002", node, "bare-except")
        if node.body and all(isinstance(stmt, ast.Pass) for stmt in node.body):
            self.add("PY003", node, f"swallowed:{_dotted_name(node.type) if node.type else 'bare'}")

    def _call(self, node: ast.Call) -> None:
        name = _dotted_name(node.func)
        short = name.rsplit(".", 1)[-1]

        if short in {"eval", "exec"} and not name.startswith("ast."):
            self.add("PY005", node, f"{name}/arity{len(node.args)}")
        if short == "compile" and name in {"compile", "builtins.compile"}:
            self.add("PY005", node, "compile")
        if name in {
            "pickle.load",
            "pickle.loads",
            "pickle.Unpickler",
            "dill.load",
            "dill.loads",
            "marshal.load",
            "marshal.loads",
            "shelve.open",
            "jsonpickle.decode",
        } or (
            short in {"load", "loads"}
            and name.startswith(("pickle", "dill", "marshal", "jsonpickle"))
        ):
            self.add("PY006", node, f"{name}")
        if short in {"load", "load_all"} and name.startswith("yaml"):
            loader = _call_keyword(node, "Loader")
            unsafe = loader is None or not (
                isinstance(loader.value, ast.Attribute) and "Safe" in loader.value.attr
            )
            if unsafe:
                loader_name = _dotted_name(loader.value) if loader else "default"
                self.add("PY007", node, f"{name}:loader={loader_name}")
        if name in {"os.system", "os.popen"}:
            self.add("PY008", node, name)
        if name == "tempfile.mktemp":
            self.add("PY009", node, "tempfile.mktemp")
        if (
            name in {"hashlib.md5", "hashlib.sha1"}
            and _call_keyword(node, "usedforsecurity") is None
        ):
            self.add("PY010", node, name)
        if (
            name.endswith("subprocess.run")
            or name.endswith("subprocess.call")
            or name
            in {
                "subprocess.run",
                "subprocess.call",
                "subprocess.check_call",
                "subprocess.check_output",
                "subprocess.Popen",
                "subprocess.getoutput",
            }
        ):
            shell = _call_keyword(node, "shell")
            if shell is not None and _is_true_literal(shell.value):
                self.add("PY004", node, f"{name}:shell=True")
            if (
                name
                in {
                    "subprocess.run",
                    "subprocess.call",
                    "subprocess.check_call",
                    "subprocess.check_output",
                }
                and _call_keyword(node, "timeout") is None
            ):
                self.add("PY013", node, f"{name}:no-timeout")
        if short in {
            "get",
            "post",
            "put",
            "delete",
            "patch",
            "head",
            "options",
            "request",
        } and name.startswith(("requests.", "httpx.", "aiohttp.", "urllib3.")):
            verify = _call_keyword(node, "verify")
            if verify is not None and _is_false_literal(verify.value):
                self.add("PY011", node, f"{name}:verify=False")
            if _call_keyword(node, "timeout") is None:
                self.add("PY013", node, f"{name}:no-timeout")

    def _unreachable(self, node: ast.AST) -> None:
        for field_name in ("body", "orelse", "finalbody"):
            block = getattr(node, field_name, None)
            if not isinstance(block, list):
                continue
            for index, stmt in enumerate(block[:-1]):
                if isinstance(stmt, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
                    following = block[index + 1]
                    if isinstance(following, (ast.Pass, ast.Expr)) and (
                        isinstance(following, ast.Pass)
                        or (
                            isinstance(following, ast.Expr)
                            and isinstance(following.value, ast.Constant)
                            and isinstance(following.value.value, str)
                        )
                    ):
                        continue
                    self.add(
                        "PY012",
                        following,
                        f"after-{type(stmt).__name__.lower()}:"
                        f"{ast.dump(following, annotate_fields=False)[:80]}",
                    )
                    break


class PythonAstAnalyzer:
    """AST-based rules for Python files with complete new-side content."""

    name = "python_ast"

    def rule_specs(self) -> Sequence[RuleSpec]:
        return tuple(SPECS.values())

    def analyze(self, context: AnalysisContext) -> Iterable[Finding]:
        if not (context.path.endswith(".py") or context.file.extension == ".py"):
            return
        factory = FindingFactory(context)
        view = context.analysis_view
        if view == "none":
            # Honest scope reporting: a partial patch cannot be parsed as a module.
            return

        line_map: tuple[int | None, ...] | None = (
            context.fragment_line_map if view == "fragment" else None
        )
        source = context.full_source if view == "complete" else context.fragment
        if source is None:
            # The view implies a source exists; if it does not, report nothing rather than
            # analysing an empty string and inventing findings.
            return

        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            # A syntax error is only a definite fact about the author's code when the view
            # is the complete file. A fragment that does not parse means the change sits
            # inside a larger block, which is a scope limitation, not a defect.
            if view == "complete" and context.file.status.value == "added":
                yield factory.create(
                    SPECS["PY014"],
                    line=factory.line_if_changed(exc.lineno),
                    message=f"Added file does not parse: {exc.msg}",
                    signature=f"syntax-error:{exc.msg}",
                    evidence=_snippet(source, exc.lineno),
                    metadata={"offset": exc.offset, "parser_line": exc.lineno},
                )
            return
        except (ValueError, MemoryError, RecursionError):
            return

        collector = _Collector(tree)
        collector.walk()
        seen: set[tuple[str, int, str]] = set()
        for rule_id, lineno, signature, note in collector.matches:
            key = (rule_id, lineno, note)
            if key in seen:
                continue
            seen.add(key)
            spec = SPECS[rule_id]
            mapped = _map_line(lineno, line_map)
            anchor = factory.line_if_changed(mapped)
            if spec.finding_class is FindingClass.DETERMINISTIC and anchor is None:
                # The construct exists in the analysed view but not on a changed line:
                # it is pre-existing code, so it is out of review scope.
                continue
            symbol = _symbol_for_lineno(tree, lineno) or (note or None)
            yield factory.create(
                spec,
                line=anchor,
                symbol=symbol,
                signature=signature,
                discriminator=str(lineno) if anchor is None else None,
                message=_message_for(spec, note),
                evidence=_snippet(source, lineno),
                metadata={"parser_line": lineno, "analysis_view": view},
            )


def _map_line(lineno: int, line_map: tuple[int | None, ...] | None) -> int | None:
    """Map a parser line number back to a new-side diff line number."""
    if line_map is None:
        return lineno
    index = lineno - 1
    if index < 0 or index >= len(line_map):
        return None
    return line_map[index]


def _message_for(spec: RuleSpec, note: str) -> str:
    if note:
        return f"{spec.title}: {note}"
    return spec.title


def _snippet(source: str, lineno: int | None, radius: int = 0) -> tuple[str, ...]:
    if not lineno:
        return ()
    lines = source.splitlines()
    start = max(0, lineno - 1 - radius)
    end = min(len(lines), lineno + radius)
    return tuple(line.rstrip() for line in lines[start:end])


__all__ = ["SPECS", "PythonAstAnalyzer"]
