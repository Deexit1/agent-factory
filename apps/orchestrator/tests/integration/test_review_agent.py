"""T-106 / SPEC-105: the Review agent — verdict handling against a real apps/api
(in_review -> in_qa/bounced), enforced end-to-end (LLM mocked)."""

import json
import urllib.request

import pytest
from schemas import AcceptanceCriterion, Complexity, TaskSpec

from orchestrator.agents import review as review_module
from orchestrator.agents.review import run_review_agent
from orchestrator.api_client import ApiClient
from orchestrator.github_client import FakeGitHubClient, PullRequest

from .conftest import SERVICE_TOKEN

_AUTH_HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}

CLEAN_DIFF = """\
diff --git a/app.py b/app.py
index 1111111..2222222 100644
--- a/app.py
+++ b/app.py
@@ -1,2 +1,5 @@
 def create_app():
     routes = {}
+    @routes.get("/health")
+    def health():
+        return {"status": "ok"}, 200
     return routes
diff --git a/test_app.py b/test_app.py
index 3333333..4444444 100644
--- a/test_app.py
+++ b/test_app.py
@@ -0,0 +1,4 @@
+def test_health_returns_200():
+    app = create_app()
+    response = app["/health"]()
+    assert response[1] == 200
"""

SCOPE_VIOLATION_DIFF = """\
diff --git a/app.py b/app.py
index 1111111..2222222 100644
--- a/app.py
+++ b/app.py
@@ -1,2 +1,5 @@
 def create_app():
     routes = {}
+    @routes.get("/health")
+    def health():
+        return {"status": "ok"}, 200
     return routes
diff --git a/unrelated_billing_module.py b/unrelated_billing_module.py
index 5555555..6666666 100644
--- a/unrelated_billing_module.py
+++ b/unrelated_billing_module.py
@@ -1,2 +1,3 @@
 def charge_card():
+    # unrelated rewrite, nothing to do with the /health endpoint task
     pass
"""


class _FakeRouteResult:
    def __init__(self, text: str) -> None:
        self.text = text
        self.model = "claude-sonnet-5"
        self.tokens_in = 300
        self.tokens_out = 150
        self.cost_usd = 0.002


def _fake_route_returning(result_json: str):
    def _route(role: str, *, system: str, messages: list[dict[str, str]], max_tokens: int):
        return _FakeRouteResult(result_json)

    return _route


def _task_spec(ticket_id: str) -> TaskSpec:
    return TaskSpec(
        id=ticket_id,
        title="Add /health endpoint",
        context="The app has no health check. Add a /health route returning 200.",
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-1",
                description="GET /health returns 200",
                verification="test_app.py::test_health_returns_200",
            )
        ],
        complexity=Complexity.LOW,
        budget_usd=20.0,
    )


def _dev_login(running_api: str, email: str, role: str) -> str:
    request = urllib.request.Request(
        f"{running_api}/auth/dev-login",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"email": email, "role": role}).encode(),
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())["token"]  # type: ignore[no-any-return]


def _approve_review(running_api: str, ticket_id: str, token: str) -> dict[str, object]:
    request = urllib.request.Request(
        f"{running_api}/tickets/{ticket_id}/approve",
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        data=json.dumps({"gate": "review", "decision": "approved"}).encode(),
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())  # type: ignore[no-any-return]


def _post_ci_failure(running_api: str, ticket_id: str) -> dict[str, object]:
    request = urllib.request.Request(
        f"{running_api}/webhooks/ci-result",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps(
            {
                "ticket_id": ticket_id,
                "conclusion": "failure",
                "suite": "unit",
                "raw_log": "FAILED test_app.py::test_health_returns_200 - assert 500 == 200",
            }
        ).encode(),
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())  # type: ignore[no-any-return]


def _ready_ticket_in_review(api: ApiClient) -> str:
    ticket = api.create_ticket(
        ticket_type="task",
        title="Add /health endpoint",
        created_by="human:test",
        budget_usd=20.0,
        acceptance_criteria=[
            {"id": "AC-1", "description": "GET /health returns 200", "verification": "v"}
        ],
    )
    ticket_id: str = ticket["id"]
    api.transition(ticket_id, to_state="in_progress", actor="human:test")
    api.transition(ticket_id, to_state="in_review", actor="agent:dev-1")
    return ticket_id


def test_scope_violation_diff_is_blocked_and_bounces_the_ticket(
    api: ApiClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1: a PR with a planted out-of-scope file edit is blocked with a
    scope_violation naming the file."""
    ticket_id = _ready_ticket_in_review(api)
    pr = PullRequest(url="https://github.com/example/repo/pull/1", number=1)
    github = FakeGitHubClient(diff=SCOPE_VIOLATION_DIFF)
    result_json = json.dumps(
        {
            "verdict": "block",
            "comments": [
                {"file": "unrelated_billing_module.py", "line": 2, "comment": "out of scope"}
            ],
            "scope_violations": ["unrelated_billing_module.py"],
        }
    )
    monkeypatch.setattr(review_module, "route", _fake_route_returning(result_json))

    result = run_review_agent(
        ticket_id=ticket_id, task_spec=_task_spec(ticket_id), pr=pr, api=api, github=github
    )

    assert result.verdict == "block"
    assert result.result.scope_violations == ["unrelated_billing_module.py"]

    ticket_after = api.get_ticket(ticket_id)
    assert ticket_after["state"] == "bounced"
    assert ticket_after["bounce_count"] == 1
    assert len(github.comments) == 1


def test_clean_diff_is_approved_and_transitions_to_in_qa(
    api: ApiClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC2: a clean fixture PR is approved and transitions to in_qa automatically."""
    ticket_id = _ready_ticket_in_review(api)
    pr = PullRequest(url="https://github.com/example/repo/pull/2", number=2)
    github = FakeGitHubClient(diff=CLEAN_DIFF)
    result_json = json.dumps({"verdict": "approve", "comments": [], "scope_violations": []})
    monkeypatch.setattr(review_module, "route", _fake_route_returning(result_json))

    result = run_review_agent(
        ticket_id=ticket_id, task_spec=_task_spec(ticket_id), pr=pr, api=api, github=github
    )

    assert result.verdict == "approve"
    ticket_after = api.get_ticket(ticket_id)
    assert ticket_after["state"] == "in_qa"
    assert len(github.comments) == 1


def test_review_bounce_then_qa_bounce_share_bounce_count(
    api: ApiClient, running_api: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC3: review-block then QA-fail on the same ticket yields bounce_count = 2
    (shared counter)."""
    ticket_id = _ready_ticket_in_review(api)
    pr = PullRequest(url="https://github.com/example/repo/pull/3", number=3)
    github = FakeGitHubClient(diff=SCOPE_VIOLATION_DIFF)
    block_json = json.dumps(
        {
            "verdict": "block",
            "comments": [{"file": "x.py", "line": None, "comment": "bad"}],
            "scope_violations": ["x.py"],
        }
    )
    monkeypatch.setattr(review_module, "route", _fake_route_returning(block_json))

    review_result = run_review_agent(
        ticket_id=ticket_id, task_spec=_task_spec(ticket_id), pr=pr, api=api, github=github
    )
    assert review_result.verdict == "block"
    assert api.get_ticket(ticket_id)["bounce_count"] == 1

    api.transition(ticket_id, to_state="in_progress", actor="human:test")
    api.transition(ticket_id, to_state="in_review", actor="agent:dev-1")
    api.transition(ticket_id, to_state="in_qa", actor="agent:review-1")

    ci_result = _post_ci_failure(running_api, ticket_id)
    assert ci_result["state"] == "bounced"
    assert ci_result["bounce_count"] == 2


def test_human_override_on_a_blocked_pr_transitions_to_in_qa_with_approval_row(
    api: ApiClient, running_api: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC4: human override on a blocked PR transitions to in_qa and records the
    approval row."""
    ticket_id = _ready_ticket_in_review(api)
    pr = PullRequest(url="https://github.com/example/repo/pull/4", number=4)
    github = FakeGitHubClient(diff=SCOPE_VIOLATION_DIFF)
    block_json = json.dumps(
        {
            "verdict": "block",
            "comments": [{"file": "x.py", "line": None, "comment": "bad"}],
            "scope_violations": ["x.py"],
        }
    )
    monkeypatch.setattr(review_module, "route", _fake_route_returning(block_json))

    run_review_agent(
        ticket_id=ticket_id, task_spec=_task_spec(ticket_id), pr=pr, api=api, github=github
    )
    assert api.get_ticket(ticket_id)["state"] == "bounced"

    token = _dev_login(running_api, "approver-review@example.com", "approver")
    approval = _approve_review(running_api, ticket_id, token)
    assert approval["gate"] == "review"

    api.transition(ticket_id, to_state="in_qa", actor="human:alice")
    ticket_after = api.get_ticket(ticket_id)
    assert ticket_after["state"] == "in_qa"
    assert ticket_after["bounce_count"] == 1
