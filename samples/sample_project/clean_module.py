"""DEMONSTRATION DATA — the cleaned-up counterpart of ``risky_module.py``.

Every planted problem from ``risky_module.py`` is corrected here in the same order. PRISM
reports **no** findings for this file: it is the negative control for the example review,
and ``tests/test_sample_project.py`` asserts that.

No ``eval``, no ``exec``, no ``shell=True``, no shared mutable defaults, no bare ``except``,
no assertion used as validation, and an explicit timeout on every blocking call.
"""

from __future__ import annotations

import ast
import hashlib
import ipaddress
import json
import logging
import operator
import os
import subprocess
import tempfile

import yaml

logger = logging.getLogger(__name__)

# SEC001 fixed: the credential is read from the environment, never stored in source.
API_KEY = os.environ.get("SAMPLE_API_KEY")

# Timeouts and TLS verification are configured once and reused.
DEFAULT_TIMEOUT_SECONDS = 10.0


def collect(items=None):  # PY001 fixed: no shared mutable default
    """Build the list inside the call, so nothing leaks between calls."""
    result = list(items) if items is not None else []
    result.append(len(result))
    return result


def run_command(arguments):  # PY004 fixed: argv form, no shell, with a timeout
    """Execute a fixed argv list. The caller supplies the arguments as a sequence."""
    if not isinstance(arguments, (list, tuple)) or not arguments:
        raise ValueError("arguments must be a non-empty sequence")
    return subprocess.run(
        list(arguments),
        check=True,
        shell=False,
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )


# A tiny allow-listed arithmetic evaluator, so no dynamic code execution is needed.
_BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def evaluate_expression(expression):
    """Evaluate a numeric expression by walking the syntax tree.

    This replaces ``eval`` with an explicit parser: only number literals and arithmetic
    operators are accepted, and the builtins namespace is never involved at all.
    """
    text = expression.strip()
    if not text or len(text) > 64:
        raise ValueError("expression is out of range")
    if not all(char in "0123456789+-*/(). %" for char in text):
        raise ValueError("expression contains characters that are not allowed")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ValueError("expression is not valid arithmetic") from exc
    return float(_evaluate_node(tree.body))


def _evaluate_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPS:
        return _BINARY_OPS[type(node.op)](_evaluate_node(node.left), _evaluate_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_evaluate_node(node.operand))
    raise ValueError("expression uses an unsupported construct")


def load_state(blob):  # PY006 fixed: data-only format
    """JSON cannot execute code while loading."""
    return json.loads(blob)


def read_config(text):  # PY007 fixed: safe loader
    """safe_load refuses to construct arbitrary Python objects."""
    return yaml.safe_load(text)


def scratch_path():  # PY009 fixed: an atomically created file
    """mkstemp creates the file, so no other process can claim the name first."""
    handle, path = tempfile.mkstemp(prefix="sample-")
    os.close(handle)
    return path


def checksum(payload):  # PY010 fixed: SHA-256 for security-relevant hashing
    return hashlib.sha256(payload).hexdigest()


def fetch(url):  # PY011 / PY013 fixed: verification on, explicit timeout
    """TLS verification stays on and the request cannot hang forever."""
    import requests

    return requests.get(url, verify=True, timeout=DEFAULT_TIMEOUT_SECONDS)


def parse(value):  # PY002 fixed: a specific exception
    """A narrow except clause leaves interrupts and other failures visible."""
    try:
        return int(value)
    except (TypeError, ValueError):
        logger.warning("value could not be parsed as an integer")
        return 0


def handle_errors():  # PY003 fixed: the error is logged and surfaced
    """The failure is logged and then re-raised, so it cannot pass unnoticed."""
    try:
        return 1 / 0
    except ZeroDivisionError as exc:
        logger.warning("division failed: %s", exc)
        raise


def early_return():  # PY012 fixed: the statement moved before the return
    message = "done"
    return message


def validate(flag):  # PY015 fixed: an explicit exception, not an assertion
    if flag <= 0:
        raise ValueError("flag must be positive")
    return flag


def is_private_address(host: str) -> bool:
    """Input validation is explicit and raises rather than assuming."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("host must be an IP address") from exc
    return address.is_private


def close_quietly(handle) -> None:
    """Resource handling: the context manager closes the handle on every path."""
    with handle as open_handle:
        for _ in open_handle:
            pass
