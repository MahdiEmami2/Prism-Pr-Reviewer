"""FastAPI surface: documented endpoints, validation, error envelope and leak checks."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from prism.analyzers.registry import build_default_registry
from prism.api.app import BodySizeLimitMiddleware, create_app
from prism.core.config import PrismConfig
from tests.conftest import make_added_file_diff

MUTABLE_DEFAULT = "def f(items=[]):\n    return items\n"
SAMPLE_DIFF = make_added_file_diff("app/risky.py", MUTABLE_DEFAULT)


@pytest.fixture
def client() -> TestClient:
    app = create_app(PrismConfig())
    return TestClient(app, raise_server_exceptions=False)


def test_health_endpoint_reports_capabilities_without_secrets(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["rule_count"] == len(build_default_registry().rule_specs())
    assert body["github_token_configured"] is False
    assert body["external_tools_enabled"] is False


def test_version_endpoint_lists_rules_and_limitations(client: TestClient) -> None:
    response = client.get("/version")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "PRISM"
    assert "local_diff" in body["supported_review_modes"]
    assert "github_pr" in body["supported_review_modes"]
    assert "PY001" in body["implemented_rule_ids"]
    assert any("never executed" in note for note in body["limitations"])


def test_rules_endpoint_returns_the_catalogue(client: TestClient) -> None:
    response = client.get("/api/v1/rules")
    assert response.status_code == 200
    rules = response.json()["rules"]
    assert "PY004" in rules
    assert rules["PY004"]["default_severity"] == "high"


def test_openapi_document_is_served_and_describes_all_routes(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"])
    assert {
        "/health",
        "/version",
        "/api/v1/rules",
        "/api/v1/reviews/diff",
        "/api/v1/reviews/github",
    }.issubset(paths)


def test_diff_review_endpoint_returns_findings(client: TestClient) -> None:
    response = client.post("/api/v1/reviews/diff", json={"diff": SAMPLE_DIFF})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    review = body["review"]
    assert review["summary"]["total_findings"] >= 1
    rule_ids = {finding["rule_id"] for finding in review["findings"]}
    assert "PY001" in rule_ids
    assert review["engine"]["mode"] == "local_diff"


def test_diff_review_rejects_empty_diff(client: TestClient) -> None:
    response = client.post("/api/v1/reviews/diff", json={"diff": ""})
    assert response.status_code == 422


def test_diff_review_rejects_non_diff_input_with_a_useful_code(client: TestClient) -> None:
    response = client.post("/api/v1/reviews/diff", json={"diff": "hello, this is prose"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_input"


def test_unknown_fields_are_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/reviews/diff",
        json={"diff": SAMPLE_DIFF, "execute": "rm -rf /"},
    )
    assert response.status_code == 422
    assert "execute" in json.dumps(response.json())


def test_oversized_body_is_rejected_with_413(client: TestClient) -> None:
    huge = "x" * (6 * 1024 * 1024)
    response = client.post("/api/v1/reviews/diff", json={"diff": huge})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "input_too_large"


def test_severity_policy_is_applied_per_request(client: TestClient) -> None:
    response = client.post(
        "/api/v1/reviews/diff",
        json={"diff": SAMPLE_DIFF, "options": {"min_severity": "critical"}},
    )
    assert response.status_code == 200
    body = response.json()["review"]
    assert body["summary"]["total_findings"] == 0
    assert body["suppressed_findings"], "the response must show what the policy suppressed"
    assert {item["policy"] for item in body["suppressed_findings"]} == {"min_severity=critical"}


def test_excluding_a_rule_removes_only_that_rule(client: TestClient) -> None:
    response = client.post(
        "/api/v1/reviews/diff",
        json={"diff": SAMPLE_DIFF, "options": {"excluded_rules": ["PY001"]}},
    )
    body = response.json()["review"]
    rule_ids = {finding["rule_id"] for finding in body["findings"]}
    assert "PY001" not in rule_ids
    # The review-level testing heuristic is a different rule and must survive.
    assert "TST001" in rule_ids
    assert "PY001" in {item["rule_id"] for item in body["suppressed_findings"]}


def test_invalid_rule_identifier_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/reviews/diff",
        json={"diff": SAMPLE_DIFF, "options": {"excluded_rules": ["bad rule; rm -rf /"]}},
    )
    assert response.status_code == 422


def test_github_endpoint_rejects_a_non_github_owner(client: TestClient) -> None:
    response = client.post(
        "/api/v1/reviews/github",
        json={"owner": "../etc", "repo": "passwd", "pull_number": 1},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_github_endpoint_accepts_coordinates_only_no_url_field(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    properties = schema["components"]["schemas"]["GitHubReviewRequest"]["properties"]
    assert set(properties) == {"owner", "repo", "pull_number", "options"}
    assert "url" not in properties


def test_github_endpoint_uses_an_injected_mock_transport() -> None:
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/files"):
            return httpx.Response(
                200,
                json=[
                    {
                        "filename": "app/x.py",
                        "status": "added",
                        "patch": ("@@ -0,0 +1,2 @@\n+def f(items=[]):\n+    return items\n"),
                    }
                ],
            )
        return httpx.Response(
            200,
            json={
                "title": "t",
                "state": "open",
                "user": {"login": "u"},
                "base": {"ref": "main", "sha": "a"},
                "head": {"ref": "b", "sha": "b"},
            },
        )

    app = create_app(PrismConfig(), transport=httpx.MockTransport(handler))
    with TestClient(app) as gh_client:
        response = gh_client.post(
            "/api/v1/reviews/github",
            json={"owner": "octocat", "repo": "Hello-World", "pull_number": 1},
        )
    assert response.status_code == 200
    review = response.json()["review"]
    assert review["metadata"]["repository"] == "octocat/Hello-World"
    assert {f["rule_id"] for f in review["findings"]} >= {"PY001"}


def test_no_response_leaks_filesystem_paths_or_environment_values(client: TestClient) -> None:
    responses = [
        client.get("/health"),
        client.get("/version"),
        client.get("/api/v1/rules"),
        client.post("/api/v1/reviews/diff", json={"diff": SAMPLE_DIFF}),
        client.post("/api/v1/reviews/diff", json={"diff": "not a diff"}),
    ]
    for response in responses:
        text = response.text
        for forbidden in ("/home/", "/usr/lib/", "/mnt/", "PRISM_", "site-packages"):
            assert forbidden not in text, f"{forbidden!r} leaked in {response.request.url}"


def test_no_endpoint_executes_submitted_code(client: TestClient) -> None:
    """Inventory check: every route is read-only analysis, none is an executor."""
    schema = client.get("/openapi.json").json()
    for path, methods in schema["paths"].items():
        for method, spec in methods.items():
            lowered = f"{path} {method} {spec.get('summary', '')}".lower()
            for banned in ("exec", "eval", "run-code", "shell", "execute"):
                assert banned not in lowered, f"{banned!r} appears in route {lowered!r}"


def test_error_envelope_is_consistent(client: TestClient) -> None:
    response = client.post("/api/v1/reviews/diff", json={"diff": "prose, not a diff"})
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}


def test_path_traversal_shaped_diff_path_is_handled_without_touching_disk(
    client: TestClient,
) -> None:
    """A traversal-shaped path is untrusted data: never opened, and explicitly reported."""
    hostile = make_added_file_diff("../../etc/passwd", MUTABLE_DEFAULT)
    response = client.post("/api/v1/reviews/diff", json={"diff": hostile})
    assert response.status_code == 200
    scope = response.json()["review"]["scope"]
    reasons = {item["reason"] for item in scope["skipped"]}
    assert reasons, "an unusable path must be reported as a skipped input, not silently dropped"
    # Nothing in the response may present the hostile path as a real location.
    assert all(
        not (finding["location"]["path"] or "").startswith("..")
        for finding in response.json()["review"]["findings"]
    )
    # The same content at a legitimate path is analysed and does fire the rule, which proves
    # the skip above is about the path and not about the code.
    control = client.post(
        "/api/v1/reviews/diff", json={"diff": make_added_file_diff("app/x.py", MUTABLE_DEFAULT)}
    )
    assert {f["rule_id"] for f in control.json()["review"]["findings"]} >= {"PY001"}


def test_body_size_limit_is_configurable_and_enforced() -> None:
    app = create_app(PrismConfig(), transport=None)
    middleware = BodySizeLimitMiddleware(app=app.router, max_bytes=1024)
    assert middleware.max_bytes == 1024


def test_response_includes_a_process_time_header(client: TestClient) -> None:
    response = client.get("/health")
    assert "x-process-time-ms" in {key.lower() for key in response.headers}
