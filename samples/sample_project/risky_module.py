"""DEMONSTRATION DATA — intentionally problematic code.

Every construct below is a planted review problem for PRISM to find. Nothing here is safe
to copy. The corrected version of each snippet is in ``clean_module.py``, and no PRISM rule
should fire on that file.

The module is written so that importing it would raise: PRISM must never import or execute
analysed code, so this file doubles as evidence of that property.
"""

from __future__ import annotations

import hashlib
import os
import pickle
import subprocess
import tempfile

import yaml

# PY001 / SEC001: mutable default argument and a hard-coded credential.
API_KEY = "hardcoded-demo-credential-value-8f3a2b"
# SEC002: PEM private key material committed to a repository.
DEMO_KEY = "-----BEGIN RSA PRIVATE KEY-----"


def collect(items=[]):  # PY001
    """A shared mutable default: the list is created once and reused across calls."""
    items.append(len(items))
    return items


def run_command(command):  # PY004
    """shell=True turns any interpolated value into shell syntax."""
    return subprocess.run(command, shell=True)


def run_legacy_command(command):  # PY008
    """os.system always goes through the shell."""
    return os.system(command)


def evaluate(expression):  # PY005
    """eval turns data into code."""
    return eval(expression)


def load_state(blob):  # PY006
    """pickle can execute code while loading."""
    return pickle.loads(blob)


def read_config(text):  # PY007
    """yaml.load without SafeLoader constructs arbitrary objects."""
    return yaml.load(text)


def scratch_path():  # PY009
    """mktemp returns a name without creating the file."""
    return tempfile.mktemp()


def checksum(payload):  # PY010
    """MD5 is collision-broken for security purposes."""
    return hashlib.md5(payload).hexdigest()


def fetch(url):  # PY011 / PY013
    """verify=False disables certificate validation, and there is no timeout."""
    import requests

    return requests.get(url, verify=False)


def parse(value):  # PY002
    """A bare except catches KeyboardInterrupt and SystemExit too."""
    try:
        return int(value)
    except:
        return 0


def ignore_errors():  # PY003
    """The exception is discarded, so the failure is invisible."""
    try:
        return 1 / 0
    except ZeroDivisionError:
        pass


def early_return():  # PY012
    """The statement after return can never run."""
    return "done"
    print("unreachable")


def validate(flag):  # PY015
    """Validation with assert disappears under python -O."""
    assert flag > 0
    return flag


def dangerous_cleanup():  # unreachable-by-design body; never called
    raise RuntimeError("demo module must not be imported or executed")
