import json
import urllib.request

from schemas import AcceptanceCriterion, Complexity, FailureReport, TaskSpec

from orchestrator.agents.dev import run_dev_agent
from orchestrator.api_client import ApiClient
from orchestrator.config import DevAgentConfig
from orchestrator.fixture_runner import FixtureClaudeCodeRunner
from orchestrator.github_client import FakeGitHubClient

from .conftest import SERVICE_TOKEN

_AUTH_HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}


def _task_spec(ticket_id: str, budget_usd: float = 5.0) -> TaskSpec:
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
        budget_usd=budget_usd,
    )


def _get_ticket(running_api: str, ticket_id: str) -> dict[str, object]:
    request = urllib.request.Request(f"{running_api}/tickets/{ticket_id}", headers=_AUTH_HEADERS)
    with urllib.request.urlopen(request) as response:
        result: dict[str, object] = json.loads(response.read())
        return result


def _get_events(running_api: str, ticket_id: str) -> list[dict[str, object]]:
    request = urllib.request.Request(
        f"{running_api}/tickets/{ticket_id}/events?limit=100", headers=_AUTH_HEADERS
    )
    with urllib.request.urlopen(request) as response:
        body: dict[str, object] = json.loads(response.read())
        items = body["items"]
        assert isinstance(items, list)
        return items


def test_agent_produces_pr_with_endpoint_and_test(
    running_api: str,
    api: ApiClient,
    config: DevAgentConfig,
    create_ticket,
    transition,
    toy_repo,
    fixture_dir,
) -> None:
    ticket = create_ticket()
    ticket_id = ticket["id"]
    transition(ticket_id, "in_progress")

    github = FakeGitHubClient()
    result = run_dev_agent(
        ticket_id=ticket_id,
        task_spec=_task_spec(ticket_id),
        workspace_dir=toy_repo,
        api=api,
        claude_runner=FixtureClaudeCodeRunner(fixture_dir),
        github=github,
        config=config,
    )

    assert result.status == "completed"
    assert result.pr_url is not None

    assert (toy_repo / "test_app.py").exists()
    app_contents = (toy_repo / "app.py").read_text()
    assert "/health" in app_contents

    assert len(github.calls) == 1
    assert github.calls[0]["branch"] == f"agent/{ticket_id}"

    ticket_after = _get_ticket(running_api, ticket_id)
    assert ticket_after["state"] == "in_qa"


def test_transcript_events_stream_incrementally(
    api: ApiClient,
    config: DevAgentConfig,
    create_ticket,
    transition,
    toy_repo,
    fixture_dir,
    running_api,
) -> None:
    ticket = create_ticket()
    ticket_id = ticket["id"]
    transition(ticket_id, "in_progress")

    run_dev_agent(
        ticket_id=ticket_id,
        task_spec=_task_spec(ticket_id),
        workspace_dir=toy_repo,
        api=api,
        claude_runner=FixtureClaudeCodeRunner(fixture_dir),
        github=FakeGitHubClient(),
        config=config,
    )

    events = _get_events(running_api, ticket_id)
    non_transition = [e for e in events if e["kind"] != "transition"]

    # 11 fixture lines -> 11 separate events, not one final summary blob.
    assert len(non_transition) == 11
    kinds_seen = {e["kind"] for e in non_transition}
    assert kinds_seen == {"message", "tool_call", "test_result", "cost"}


def test_low_budget_escalates_before_completion(
    running_api: str,
    api: ApiClient,
    config: DevAgentConfig,
    create_ticket,
    transition,
    toy_repo,
    fixture_dir,
) -> None:
    ticket = create_ticket(budget_usd=0.01)
    ticket_id = ticket["id"]
    transition(ticket_id, "in_progress")

    result = run_dev_agent(
        ticket_id=ticket_id,
        task_spec=_task_spec(ticket_id, budget_usd=0.01),
        workspace_dir=toy_repo,
        api=api,
        claude_runner=FixtureClaudeCodeRunner(fixture_dir),
        github=FakeGitHubClient(),
        config=config,
    )

    assert result.status == "budget_exceeded"
    assert result.pr_url is None

    ticket_after = _get_ticket(running_api, ticket_id)
    assert ticket_after["state"] == "escalated"

    # Broke out before the fixture's tail end ever ran, so no diff was ever applied.
    assert not (toy_repo / "test_app.py").exists()


def test_bounce_injects_failure_report_and_attempt_number(
    api: ApiClient, config: DevAgentConfig, create_ticket, transition, toy_repo, fixture_dir
) -> None:
    ticket = create_ticket()
    ticket_id = ticket["id"]
    transition(ticket_id, "in_progress")

    failure_report = FailureReport(
        ticket_id=ticket_id,
        failing_suite="pytest",
        failing_tests=["test_app.py::test_health_returns_200"],
        expected_vs_actual="expected 200, got 404",
        suspect_files=["app.py"],
        attempt_no=2,
    )
    runner = FixtureClaudeCodeRunner(fixture_dir)

    run_dev_agent(
        ticket_id=ticket_id,
        task_spec=_task_spec(ticket_id),
        workspace_dir=toy_repo,
        api=api,
        claude_runner=runner,
        github=FakeGitHubClient(),
        config=config,
        failure_report=failure_report,
        attempt_no=2,
    )

    assert runner.last_prompt is not None
    assert "attempt 2" in runner.last_prompt
    assert "expected 200, got 404" in runner.last_prompt
    assert "test_app.py::test_health_returns_200" in runner.last_prompt
    assert "app.py" in runner.last_prompt


def test_cost_ledger_total_matches_agent_runs_total(
    api: ApiClient, config: DevAgentConfig, create_ticket, transition, toy_repo, fixture_dir
) -> None:
    ticket = create_ticket()
    ticket_id = ticket["id"]
    transition(ticket_id, "in_progress")

    run_dev_agent(
        ticket_id=ticket_id,
        task_spec=_task_spec(ticket_id),
        workspace_dir=toy_repo,
        api=api,
        claude_runner=FixtureClaudeCodeRunner(fixture_dir),
        github=FakeGitHubClient(),
        config=config,
    )

    summary = api.cost_summary(ticket_id)
    assert summary["agent_runs_total_usd"] == summary["cost_ledger_total_usd"]
    assert summary["agent_runs_total_usd"] == 0.021
