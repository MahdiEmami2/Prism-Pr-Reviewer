"""Secret rules and credential redaction.

The placeholder safeguards get their own tests, because a secret scanner that cries wolf on
``password = "changeme"`` is worse than useless.
"""

from __future__ import annotations

import logging

import pytest

from prism.analyzers.secrets import entropy_is_secret_like, is_placeholder
from prism.core.logging_setup import RedactionFilter
from prism.core.redaction import redact, redact_mapping, safe_env_names
from tests.conftest import has_rule, make_added_file_diff, review_code, review_diff

# --------------------------------------------------------------- SEC001


def test_sec001_positive_literal_password() -> None:
    result = review_code('password = "hunter2-but-longer"\n')
    matching = [f for f in result.findings if f.rule_id == "SEC001"]
    assert matching
    assert matching[0].confidence.value == "medium"


def test_sec001_negative_environment_lookup() -> None:
    for line in (
        "password = os.environ['DB_PASSWORD']\n",
        "api_key = os.getenv('API_KEY')\n",
        "token = settings.TOKEN\n",
        'secret = config.get("secret")\n',
    ):
        assert not has_rule(review_code(line), "SEC001"), line


def test_sec001_negative_obvious_placeholders_are_not_reported() -> None:
    placeholders = [
        'password = "changeme"',
        'password = "CHANGE_ME"',
        'api_key = "your_api_key_here"',
        'token = "<your-token>"',
        'secret = "${SECRET_VALUE}"',
        'password = "xxxxxxxx"',
        'api_key = "0000000000"',
        'token = "example_token_value"',
        'password = ""',
        'secret = "TODO"',
        'api_key = "%s"',
        'token = "abcdefghij"',  # sequential-run guard
        'token = "9876543210"',
    ]
    for line in placeholders:
        parsed = review_diff(make_added_file_diff("conf/settings.py", line + "\n"))
        assert not [f for f in parsed.findings if f.rule_id == "SEC001"], (
            f"placeholder falsely reported: {line}"
        )


def test_sec001_boundary_short_value_is_ignored() -> None:
    assert not has_rule(review_code('token = "abc"\n'), "SEC001")


def test_sec001_reports_in_non_python_files_too() -> None:
    result = review_code('api_key: "s3cr3t-value-that-is-long"\n', path="config/app.yaml")
    assert has_rule(result, "SEC001")


# --------------------------------------------------------------- SEC002


def test_sec002_positive_private_key_header() -> None:
    code = 'KEY = "-----BEGIN RSA PRIVATE KEY-----"\n'
    result = review_code(code)
    matching = [f for f in result.findings if f.rule_id == "SEC002"]
    assert matching
    assert matching[0].severity.value == "critical"
    assert matching[0].confidence.value == "high"


def test_sec002_negative_public_key_and_certificate_headers() -> None:
    for line in (
        'K = "-----BEGIN PUBLIC KEY-----"',
        'K = "-----BEGIN CERTIFICATE-----"',
    ):
        assert not has_rule(review_code(line + "\n"), "SEC002"), line


# --------------------------------------------------------------- SEC003


def test_sec003_positive_high_entropy_literal_next_to_secret_name() -> None:
    literal = "Zk8sQ2vL9nB4xT7mR1pW3yA6cD5fG0hJ2kL4mN8p"
    # The name is not credential-shaped (so SEC001 stays silent) but a secret-like word is
    # present on the same line, which is what the entropy heuristic keys on.
    result = review_code(f'payload = "{literal}"  # rotated secret value\n')
    matching = [f for f in result.findings if f.rule_id == "SEC003"]
    assert matching
    assert matching[0].deterministic is False
    assert matching[0].confidence.value == "low"


def test_sec003_negative_ordinary_text_and_hashes_are_not_flagged() -> None:
    for line in (
        'secret_note = "this is a normal descriptive sentence about caching behaviour"',
        'secret_name = "a" * 30',
    ):
        assert not has_rule(review_code(line + "\n"), "SEC003"), line


def test_entropy_helper_boundaries() -> None:
    assert entropy_is_secret_like("Zk8sQ2vL9nB4xT7mR1pW3yA6cD5fG0hJ2kL4mN8p") is True
    assert entropy_is_secret_like("aaaaaaaaaaaaaaaaaaaaaaaa") is False
    assert entropy_is_secret_like("short") is False
    # A long text with spaces is not a single token, so it is out of scope for SEC003.
    assert entropy_is_secret_like("words with spaces in a sentence here") is False


def test_is_placeholder_is_a_first_class_guarantee() -> None:
    assert is_placeholder("changeme") is True
    assert is_placeholder("${VAR}") is True
    assert is_placeholder("") is True
    assert is_placeholder("x" * 40) is True
    assert is_placeholder("abcdefghij") is True
    assert is_placeholder("1234567890") is True
    assert is_placeholder("a-perfectly-real-looking-secret-value") is False
    assert is_placeholder("Zk8sQ2vL9nB4xT7mR1pW3yA6cD5fG0hJ2kL4mN8p") is False


def test_finding_evidence_does_not_echo_the_whole_secret() -> None:
    # The literal deliberately avoids sequential runs so the placeholder guard does not
    # suppress it; it is still obviously a test value, not a real credential.
    literal = "Kf9Zt2Wq7Xb4Lm8Rc3Yh5"
    result = review_code(f'api_key = "{literal}"\n')
    matching = [f for f in result.findings if f.rule_id == "SEC001"]
    assert matching
    assert literal not in matching[0].message
    assert "*" in matching[0].message


# --------------------------------------------------------------- redaction


@pytest.mark.parametrize(
    "raw",
    [
        "token ghp_abcdefghijklmnopqrstuvwxyz012345",
        "Authorization: Bearer abcdefghijklmnopqrstuvwx",
        "password=hunter2hunter2",
        "api_key: 1234567890abcdef1234567890abcdef",
        "AKIAIOSFODNN7EXAMPLE",
    ],
)
def test_redact_removes_credential_shapes(raw: str) -> None:
    cleaned = redact(raw)
    assert "[REDACTED" in cleaned


def test_redact_leaves_ordinary_text_untouched() -> None:
    text = "Found 3 findings in app/main.py at line 42."
    assert redact(text) == text


def test_redact_mapping_keeps_keys_and_masks_values() -> None:
    cleaned = redact_mapping({"token": "ghp_abcdefghijklmnopqrstuvwxyz012345", "name": "ok"})
    assert cleaned["name"] == "ok"
    assert "ghp_" not in cleaned["token"]


def test_logging_filter_scrubs_secrets_from_messages_and_arguments() -> None:
    record = logging.LogRecord(
        name="prism.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="using token %s",
        args=("ghp_abcdefghijklmnopqrstuvwxyz012345",),
        exc_info=None,
    )
    assert RedactionFilter().filter(record) is True
    rendered = record.getMessage()
    assert "ghp_" not in rendered
    assert "[REDACTED" in rendered


def test_safe_env_names_reports_names_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_abcdefghijklmnopqrstuvwxyz012345")
    names = safe_env_names()
    assert "GITHUB_TOKEN" in names
    assert all("ghp_" not in name for name in names)


def test_config_never_exposes_the_token_value() -> None:
    from prism.core.config import PrismConfig

    cfg = PrismConfig(github_token="ghp_abcdefghijklmnopqrstuvwxyz012345")
    assert cfg.has_github_token is True
    summary = cfg.safe_summary()
    assert summary["github_token_configured"] is True
    assert "ghp_" not in str(summary)


def test_config_reads_token_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    from prism.core.config import PrismConfig

    monkeypatch.setenv("PRISM_GITHUB_TOKEN", "ghp_abcdefghijklmnopqrstuvwxyz012345")
    cfg = PrismConfig.from_env()
    assert cfg.has_github_token is True
    assert "ghp_" not in str(cfg.safe_summary())
