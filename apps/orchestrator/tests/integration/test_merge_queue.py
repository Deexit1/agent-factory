"""T-107 / SPEC-106: the merge-queue processor — real git rebase/merge/conflict
mechanics against real local git fixture repos. No mocked git and no real
GitHub — `FakeGitHubClient(repo_url=...)` performs a REAL git push to simulate
what GitHub's merge would do, since the queue's serialization logic (does a
second ticket's rebase really conflict against a first ticket's real merge?) is
exactly what's under test here."""

import os
import subprocess
from pathlib import Path

from schemas import DEFAULT_REPO

from orchestrator.api_client import ApiClient
from orchestrator.github_client import FakeGitHubClient
from orchestrator.merge_queue import run_merge_queue

_GIT_IDENTITY = ["-c", "user.email=merge-queue-test@example.com", "-c", "user.name=Test"]
_NO_EDITOR_ENV = {**os.environ, "GIT_EDITOR": "true"}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def _init_bare_origin(tmp_path: Path, name: str = "origin.git") -> Path:
    origin = tmp_path / name
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True, capture_output=True
    )
    seed = tmp_path / f"{name}-seed"
    subprocess.run(
        ["git", "clone", "--quiet", str(origin), str(seed)], check=True, capture_output=True
    )
    (seed / "README.md").write_text("seed\n")
    _git(seed, "add", "-A")
    _git(seed, *_GIT_IDENTITY, "commit", "-q", "-m", "seed")
    _git(seed, "push", "-q", "origin", "main")
    return origin


def _push_ticket_branch(
    origin_url: str, ticket_id: str, *, filename: str, content: str, tmp_path: Path
) -> None:
    """Simulates the dev agent: a fresh clone of origin's main, a branch
    `agent/{ticket_id}` (matching agents/dev.py's own naming convention exactly),
    one commit, pushed."""
    clone = tmp_path / f"push-{ticket_id}"
    subprocess.run(
        ["git", "clone", "--quiet", origin_url, str(clone)], check=True, capture_output=True
    )
    _git(clone, "checkout", "-q", "-b", f"agent/{ticket_id}")
    (clone / filename).write_text(content)
    _git(clone, "add", "-A")
    _git(clone, *_GIT_IDENTITY, "commit", "-q", "-m", ticket_id)
    _git(clone, "push", "-q", "origin", f"agent/{ticket_id}")


def _ready_ticket_enqueued(api: ApiClient, title: str) -> str:
    ticket = api.create_ticket(
        ticket_type="task",
        title=title,
        created_by="human:test",
        budget_usd=20.0,
        acceptance_criteria=[{"id": "AC-1", "description": "d", "verification": "v"}],
    )
    ticket_id: str = ticket["id"]
    api.transition(ticket_id, to_state="in_progress", actor="human:test")
    api.transition(ticket_id, to_state="in_review", actor="agent:dev-1")
    api.transition(ticket_id, to_state="in_qa", actor="agent:review-1")
    api.report_ci_result(ticket_id, conclusion="success")
    return ticket_id


def _resolve_conflict_and_requeue(
    api: ApiClient,
    origin_url: str,
    ticket_id: str,
    *,
    filename: str,
    resolved_content: str,
    tmp_path: Path,
) -> None:
    """Mirrors what a real dev agent does after a conflict bounce: rebase onto
    the now-updated main on its OWN branch, resolve the conflict for real, push
    the result, then go through a fresh in_progress -> ... -> CI-green cycle so
    it re-enters the queue with a new entry."""
    clone = tmp_path / f"resolve-{ticket_id}"
    subprocess.run(
        ["git", "clone", "--quiet", "--branch", f"agent/{ticket_id}", origin_url, str(clone)],
        check=True,
        capture_output=True,
    )
    _git(clone, "config", "user.email", "merge-queue-test@example.com")
    _git(clone, "config", "user.name", "Test")
    _git(clone, "fetch", "origin", "main")
    rebase = subprocess.run(
        ["git", "rebase", "origin/main"], cwd=clone, capture_output=True, text=True
    )
    assert rebase.returncode != 0, "expected a real conflict to resolve"

    (clone / filename).write_text(resolved_content)
    _git(clone, "add", filename)
    subprocess.run(
        ["git", "-C", str(clone), "rebase", "--continue"],
        check=True,
        capture_output=True,
        text=True,
        env=_NO_EDITOR_ENV,
    )
    _git(clone, "push", "-q", "--force-with-lease", "origin", f"agent/{ticket_id}")

    api.transition(ticket_id, to_state="in_progress", actor="human:test")
    api.transition(ticket_id, to_state="in_review", actor="agent:dev-1")
    api.transition(ticket_id, to_state="in_qa", actor="agent:review-1")
    api.report_ci_result(ticket_id, conclusion="success")


def test_two_tickets_editing_the_same_file_first_merges_second_conflicts_then_succeeds(
    api: ApiClient, tmp_path: Path
) -> None:
    """AC1: two tickets editing the same file — first merges; second gets a
    conflict bounce and succeeds after agent rebase."""
    origin = _init_bare_origin(tmp_path)
    origin_url = str(origin)
    workspace_root = tmp_path / "scratch"
    workspace_root.mkdir()
    github = FakeGitHubClient(repo_url=origin_url)

    ticket_a = _ready_ticket_enqueued(api, "Ticket A")
    _push_ticket_branch(
        origin_url,
        ticket_a,
        filename="shared.py",
        content="value = 2  # from A\n",
        tmp_path=tmp_path,
    )
    github.open_pr(branch=f"agent/{ticket_a}", base="main", title="A", body="")

    ticket_b = _ready_ticket_enqueued(api, "Ticket B")
    _push_ticket_branch(
        origin_url,
        ticket_b,
        filename="shared.py",
        content="value = 3  # from B\n",
        tmp_path=tmp_path,
    )
    github.open_pr(branch=f"agent/{ticket_b}", base="main", title="B", body="")

    result = run_merge_queue(
        api=api,
        github=github,
        repo_url=origin_url,
        workspace_root=workspace_root,
        repo=DEFAULT_REPO,
    )

    assert len(result.processed) == 2
    outcome_a = next(o for o in result.processed if o.ticket_id == ticket_a)
    outcome_b = next(o for o in result.processed if o.ticket_id == ticket_b)
    assert outcome_a.outcome == "merged"
    assert outcome_b.outcome == "conflict"
    assert "shared.py" in outcome_b.conflicting_paths

    assert api.get_ticket(ticket_a)["state"] == "done"
    ticket_b_after = api.get_ticket(ticket_b)
    assert ticket_b_after["state"] == "bounced"
    assert ticket_b_after["bounce_count"] == 1

    assert list(workspace_root.iterdir()) == []  # no orphaned scratch clones

    _resolve_conflict_and_requeue(
        api,
        origin_url,
        ticket_b,
        filename="shared.py",
        resolved_content="value = 4  # resolved by dev agent\n",
        tmp_path=tmp_path,
    )

    result_2 = run_merge_queue(
        api=api,
        github=github,
        repo_url=origin_url,
        workspace_root=workspace_root,
        repo=DEFAULT_REPO,
    )
    outcome_b_2 = next(o for o in result_2.processed if o.ticket_id == ticket_b)
    assert outcome_b_2.outcome == "merged"
    assert api.get_ticket(ticket_b)["state"] == "done"
    assert list(workspace_root.iterdir()) == []


def test_load_five_tickets_three_independent_two_conflicting(
    api: ApiClient, tmp_path: Path
) -> None:
    """Load test (SPEC-106): 5 tickets — 3 independent (never conflict) and 2
    sharing a file (exercises the conflict path within the same run). All 5 end
    at done/escalated; zero orphaned scratch directories."""
    origin = _init_bare_origin(tmp_path, name="load-origin.git")
    origin_url = str(origin)
    workspace_root = tmp_path / "load-scratch"
    workspace_root.mkdir()
    github = FakeGitHubClient(repo_url=origin_url)

    independent_ids = []
    for i in range(3):
        ticket_id = _ready_ticket_enqueued(api, f"Independent {i}")
        _push_ticket_branch(
            origin_url,
            ticket_id,
            filename=f"file_{i}.py",
            content=f"value = {i}\n",
            tmp_path=tmp_path,
        )
        github.open_pr(branch=f"agent/{ticket_id}", base="main", title=ticket_id, body="")
        independent_ids.append(ticket_id)

    conflict_first = _ready_ticket_enqueued(api, "Conflict first")
    _push_ticket_branch(
        origin_url,
        conflict_first,
        filename="shared.py",
        content="value = 100\n",
        tmp_path=tmp_path,
    )
    github.open_pr(branch=f"agent/{conflict_first}", base="main", title="cf", body="")

    conflict_second = _ready_ticket_enqueued(api, "Conflict second")
    _push_ticket_branch(
        origin_url,
        conflict_second,
        filename="shared.py",
        content="value = 200\n",
        tmp_path=tmp_path,
    )
    github.open_pr(branch=f"agent/{conflict_second}", base="main", title="cs", body="")

    result = run_merge_queue(
        api=api,
        github=github,
        repo_url=origin_url,
        workspace_root=workspace_root,
        repo=DEFAULT_REPO,
    )
    assert len(result.processed) == 5
    assert list(workspace_root.iterdir()) == []

    for ticket_id in independent_ids:
        assert api.get_ticket(ticket_id)["state"] == "done"
    assert api.get_ticket(conflict_first)["state"] == "done"
    conflict_second_after = api.get_ticket(conflict_second)
    assert conflict_second_after["state"] == "bounced"

    _resolve_conflict_and_requeue(
        api,
        origin_url,
        conflict_second,
        filename="shared.py",
        resolved_content="value = 300  # resolved\n",
        tmp_path=tmp_path,
    )
    result_2 = run_merge_queue(
        api=api,
        github=github,
        repo_url=origin_url,
        workspace_root=workspace_root,
        repo=DEFAULT_REPO,
    )
    assert result_2.processed[0].outcome == "merged"
    assert list(workspace_root.iterdir()) == []

    all_ticket_ids = [*independent_ids, conflict_first, conflict_second]
    for ticket_id in all_ticket_ids:
        final_state = api.get_ticket(ticket_id)["state"]
        assert final_state in ("done", "escalated"), (ticket_id, final_state)
