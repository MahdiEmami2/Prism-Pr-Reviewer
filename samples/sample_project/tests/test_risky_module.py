"""DEMONSTRATION DATA — minimal tests for the sample module.

The presence of this file means a review that changes only ``risky_module.py`` will trigger
the "source changed without a test change" heuristic, while a review that changes both files
will not. That behaviour is asserted in ``tests/test_sample_project.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clean_module import (  # noqa: E402
    collect,
    handle_errors,
    parse,
    validate,
)


def test_collect_does_not_share_state_between_calls() -> None:
    assert collect() == [0]
    assert collect() == [0]


def test_collect_copies_the_caller_list() -> None:
    supplied = ["a"]
    collect(supplied)
    assert supplied == ["a"]


def test_parse_returns_zero_for_unparseable_input() -> None:
    assert parse("not a number") == 0
    assert parse("41") == 41


def test_handle_errors_propagates() -> None:
    with pytest.raises(ZeroDivisionError):
        handle_errors()


def test_validate_rejects_non_positive_values() -> None:
    assert validate(1) == 1
    with pytest.raises(ValueError):
        validate(0)
