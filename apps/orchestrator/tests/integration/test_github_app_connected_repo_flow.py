"""T-203 (SPEC-203 AC1): "push to their default branch is impossible" — proven at the
git-object level against a real local bare git repo standing in for "the customer
repo" (the same technique toy_repo/FakeGitHubClient.merge_pr already use elsewhere in
this test suite for "GitHub"). This proves OUR OWN mechanism (git_ops.py's agent/*-only
push guard, exercised through the real run_dev_agent code path, not mocked away);
GitHub's own server-side branch-protection enforcement against a real customer org is
disclosed as unexercised in this environment (no live GitHub App, no live customer
repo — see docs/06-tech-stack.md's implementation-status note).
"""

import subprocess
from pathlib import Path

from schemas import AcceptanceCriterion, Complexity, TaskSpec, agent_branch_name

from orchestrator import git_ops
from orchestrator.agents.dev import run_dev_agent
from orchestrator.api_client import ApiClient
from orchestrator.config import DevAgentConfig
from orchestrator.fixture_runner import FixtureClaudeCodeRunner
from orchestrator.github_client import FakeGitHubClient


def _bare_origin(tmp_path: Path) -> Path:
    origin = tmp_path / "customer-origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    return origin


def _clone_and_seed(origin: Path, workdir: Path) -> Path:
    repo = workdir / "customer-repo"
    repo.mkdir()

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    git("remote", "add", "origin", str(origin))
    (repo / "app.py").write_text("def create_app():\n    routes = {}\n    return routes\n")
    git("add", "app.py")
    git("commit", "-q", "-m", "initial commit")
    git("push", "-q", "origin", "main")
    return repo


def _origin_main_ref(origin: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(origin), "rev-parse", "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _origin_has_branch(origin: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(origin), "rev-parse", "--verify", f"refs/heads/{branch}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


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
        budget_usd=5.0,
    )


def test_dev_agent_never_touches_the_default_branch_of_a_real_customer_repo_standin(
    tmp_path: Path,
    api: ApiClient,
    config: DevAgentConfig,
    create_ticket,
    transition,
    fixture_dir,
) -> None:
    """AC1's literal "rejected test": a real bare git repo stands in for the customer's
    GitHub repo. Before/after a full run_dev_agent() run, main's ref is byte-identical
    — proven at the git-object level, not by asserting a mock was/wasn't called."""
    origin = _bare_origin(tmp_path)
    workspace = _clone_and_seed(origin, tmp_path)
    main_ref_before = _origin_main_ref(origin)

    ticket = create_ticket()
    ticket_id = ticket["id"]
    transition(ticket_id, "in_progress")
    branch = agent_branch_name(ticket_id)
    assert not _origin_has_branch(origin, branch)

    github = FakeGitHubClient()
    result = run_dev_agent(
        ticket_id=ticket_id,
        task_spec=_task_spec(ticket_id),
        workspace_dir=workspace,
        api=api,
        claude_runner=FixtureClaudeCodeRunner(fixture_dir),
        github=github,
        config=config,
        base_branch="main",
    )

    assert result.status == "completed"
    assert len(github.calls) == 1
    assert github.calls[0]["branch"] == branch
    assert github.calls[0]["base"] == "main"

    # The real assertion: main's ref in the "customer repo" is byte-identical to
    # before — the agent's push genuinely never touched it — while the agent/*
    # branch really was created there.
    assert _origin_main_ref(origin) == main_ref_before
    assert _origin_has_branch(origin, branch)


def test_git_ops_push_refuses_main_even_if_a_caller_tried(tmp_path: Path) -> None:
    """The unconditional half of AC1 — independent of run_dev_agent's own branch
    naming, git_ops.push itself refuses any non-agent/* target before touching the
    network, proven here against a REAL git repo (not a monkeypatched subprocess.run
    like test_git_ops.py's unit test — this is the integration-level confirmation)."""
    origin = _bare_origin(tmp_path)
    workspace = _clone_and_seed(origin, tmp_path)
    main_ref_before = _origin_main_ref(origin)

    (workspace / "app.py").write_text("def create_app():\n    return {}\n")
    subprocess.run(["git", "-C", str(workspace), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(workspace), "commit", "-q", "-m", "attempted direct edit"],
        check=True,
    )

    try:
        git_ops.push(workspace, "main")
        raised = False
    except git_ops.BranchNotAllowed:
        raised = True

    assert raised
    assert _origin_main_ref(origin) == main_ref_before
