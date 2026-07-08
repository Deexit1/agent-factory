"""T-109 (SPEC-102..106): the full management chain, once, for real — idea -> planner
-> budget approval -> Delivery Manager -> 2 parallel profile agents -> review -> QA ->
merge queue -> done. Every step goes through `ApiClient`/a real agent function; nothing
here ever imports a DB session or an ORM model directly, so "zero manual DB touches"
(AC2) is a structural property of this file, not a runtime assertion.

Real Anthropic spend is $0: planner/Delivery Manager/review all mock `route()` (same
pattern as their own dedicated test files), and both dev-agent legs replay a canned
`FixtureClaudeCodeRunner` transcript instead of invoking the real `claude` CLI. Only
`run_merge_queue` (pure git, no LLM) runs unmodified. This keeps a nightly run of this
test immune to the Anthropic API credit exhaustion this project has hit before on real
eval runs.
"""

import json
import re
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from schemas import DEFAULT_REPO, AcceptanceCriterion, Complexity, TaskSpec

from orchestrator.agents import delivery_manager as delivery_manager_module
from orchestrator.agents import planner as planner_module
from orchestrator.agents import review as review_module
from orchestrator.agents.delivery_manager import run_delivery_manager_agent
from orchestrator.agents.dev import DevAgentResult, run_dev_agent
from orchestrator.agents.planner import run_planner_agent
from orchestrator.agents.review import run_review_agent
from orchestrator.api_client import ApiClient
from orchestrator.capability_registry import Profile
from orchestrator.config import DevAgentConfig, scenario_cost_cap_usd
from orchestrator.fixture_runner import FixtureClaudeCodeRunner
from orchestrator.github_client import FakeGitHubClient
from orchestrator.merge_queue import run_merge_queue

from .conftest import SERVICE_TOKEN

_AUTH_HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}
_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"

_FRONTEND_PROFILE = Profile(
    id="dev-frontend",
    model="claude-sonnet-5",
    base_image="agent-factory-sandbox:latest",
    skills=("frontend",),
    max_parallel=2,
)
_BACKEND_PROFILE = Profile(
    id="dev-backend",
    model="claude-sonnet-5",
    base_image="agent-factory-sandbox:latest",
    skills=("backend",),
    max_parallel=2,
)

_FRONTEND_DIFF = """\
diff --git a/frontend.py b/frontend.py
index 1111111..2222222 100644
--- a/frontend.py
+++ b/frontend.py
@@ -1 +1,2 @@
-def render_nav(): ...
+def render_nav():
+    return ["home", "settings"]
"""

_BACKEND_DIFF = """\
diff --git a/backend.py b/backend.py
index 3333333..4444444 100644
--- a/backend.py
+++ b/backend.py
@@ -1 +1,2 @@
-def triage_queue(): ...
+def triage_queue():
+    return []
"""


class _FakeRouteResult:
    def __init__(self, text: str, *, cost_usd: float, model: str = "claude-sonnet-5") -> None:
        self.text = text
        self.model = model
        self.provider = "anthropic"
        self.tokens_in = 400
        self.tokens_out = 200
        self.cost_usd = cost_usd


def _planner_plan_json() -> str:
    return json.dumps(
        {
            "epics": [
                {
                    "id": "epic-1",
                    "title": "Triage dashboard",
                    "description": "Frontend + backend halves of the triage flow.",
                    "budget_usd": 60.0,
                }
            ],
            "tasks": [
                {
                    "id": "task-fe",
                    "title": "Add nav bar",
                    "context": "Users need a nav bar to reach the triage queue.",
                    "acceptance_criteria": [
                        {"id": "AC-1", "description": "d", "verification": "v"}
                    ],
                    "complexity": "low",
                    "budget_usd": 20.0,
                    "depends_on": [],
                    "epic_id": "epic-1",
                    "required_skills": ["frontend"],
                },
                {
                    "id": "task-be",
                    "title": "Add triage queue helper",
                    "context": "Backend needs a queue helper for the nav bar to call.",
                    "acceptance_criteria": [
                        {"id": "AC-1", "description": "d", "verification": "v"}
                    ],
                    "complexity": "low",
                    "budget_usd": 20.0,
                    "depends_on": [],
                    "epic_id": "epic-1",
                    "required_skills": ["backend"],
                },
            ],
        }
    )


def _assign_matching_profiles(profile_by_task_id: dict[str, str]):
    def _route(
        role: str,
        *,
        credentials: object,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int,
    ):
        user_message = messages[0]["content"]
        task_ids = re.findall(r"- id: (\S+)", user_message)
        assignments = [
            {
                "task_id": tid,
                "profile": profile_by_task_id[tid],
                "reason": "matches required skill",
                "alternatives": [],
            }
            for tid in task_ids
            if tid in profile_by_task_id
        ]
        return _FakeRouteResult(
            json.dumps({"assignments": assignments, "deferred": []}), cost_usd=0.002
        )

    return _route


def _approve_json() -> str:
    return json.dumps({"verdict": "approve", "comments": [], "scope_violations": []})


def _dev_login(running_api: str, email: str, role: str) -> str:
    request = urllib.request.Request(
        f"{running_api}/auth/dev-login",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"email": email, "role": role}).encode(),
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())["token"]  # type: ignore[no-any-return]


def _approve_budget(running_api: str, ticket_id: str, token: str) -> None:
    request = urllib.request.Request(
        f"{running_api}/tickets/{ticket_id}/approve",
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        data=json.dumps({"gate": "budget", "decision": "approved"}).encode(),
    )
    urllib.request.urlopen(request)


def _get_events(running_api: str, ticket_id: str) -> list[dict[str, object]]:
    request = urllib.request.Request(
        f"{running_api}/tickets/{ticket_id}/events?limit=100", headers=_AUTH_HEADERS
    )
    with urllib.request.urlopen(request) as response:
        body: dict[str, object] = json.loads(response.read())
        items = body["items"]
        assert isinstance(items, list)
        return items


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def _init_shared_origin(tmp_path: Path) -> Path:
    """A single bare origin seeded with BOTH files the two parallel tasks will edit,
    so their branches merge cleanly (disjoint files) instead of conflicting - T-107's
    conflict path is already covered by test_merge_queue.py, not this scenario."""
    origin = tmp_path / "e2e-origin.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True, capture_output=True
    )
    seed = tmp_path / "e2e-origin-seed"
    subprocess.run(
        ["git", "clone", "--quiet", str(origin), str(seed)], check=True, capture_output=True
    )
    _git(seed, "config", "user.email", "test@example.com")
    _git(seed, "config", "user.name", "Test")
    (seed / "frontend.py").write_text("def render_nav(): ...\n")
    (seed / "backend.py").write_text("def triage_queue(): ...\n")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "seed")
    _git(seed, "push", "-q", "origin", "main")
    return origin


def _clone_for_task(origin: Path, tmp_path: Path, name: str) -> Path:
    dest = tmp_path / name
    subprocess.run(
        ["git", "clone", "--quiet", str(origin), str(dest)], check=True, capture_output=True
    )
    _git(dest, "config", "user.email", "test@example.com")
    _git(dest, "config", "user.name", "Test")
    return dest


def test_idea_to_done_through_the_full_management_chain(
    api: ApiClient,
    running_api: str,
    config: DevAgentConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 1. Idea -> planner
    idea = api.create_ticket(
        ticket_type="idea",
        title="Triage dashboard",
        created_by="human:test",
        budget_usd=100.0,
    )
    api.transition(idea["id"], to_state="planning", actor="human:test")

    monkeypatch.setattr(
        planner_module,
        "route",
        lambda *a, **k: _FakeRouteResult(
            _planner_plan_json(), cost_usd=0.03, model="claude-opus-4-8"
        ),
    )
    planner_result = run_planner_agent(
        ticket_id=idea["id"],
        idea_title=idea["title"],
        idea_description="",
        idea_budget_usd=100.0,
        api=api,
    )
    assert planner_result.status == "planned"

    descendants = api.descendants(idea["id"])
    tasks = [d for d in descendants if d["type"] == "task"]
    frontend_task = next(t for t in tasks if t["spec"]["required_skills"] == ["frontend"])
    backend_task = next(t for t in tasks if t["spec"]["required_skills"] == ["backend"])

    # 2. Budget approval -> ready (cascades epic/tasks to ready)
    token = _dev_login(running_api, "approver-e2e@example.com", "approver")
    _approve_budget(running_api, idea["id"], token)
    api.transition(idea["id"], to_state="ready", actor="human:test")

    # 3. Delivery Manager assigns each task to its one skill-eligible profile
    monkeypatch.setattr(
        delivery_manager_module,
        "route",
        _assign_matching_profiles(
            {frontend_task["id"]: "dev-frontend", backend_task["id"]: "dev-backend"}
        ),
    )
    dm_result = run_delivery_manager_agent(api=api)
    outcome_fe = next(o for o in dm_result.outcomes if o.ticket_id == frontend_task["id"])
    outcome_be = next(o for o in dm_result.outcomes if o.ticket_id == backend_task["id"])
    assert outcome_fe.decision == "assigned" and outcome_fe.profile == "dev-frontend"
    assert outcome_be.decision == "assigned" and outcome_be.profile == "dev-backend"

    # 4. Two real dev-agent runs, genuinely concurrent, editing disjoint files in
    # clones of one shared origin.
    origin = _init_shared_origin(tmp_path)
    origin_url = str(origin)
    fe_workspace = _clone_for_task(origin, tmp_path, "fe-workspace")
    be_workspace = _clone_for_task(origin, tmp_path, "be-workspace")
    github = FakeGitHubClient(repo_url=origin_url)

    def _run_fe() -> DevAgentResult:
        fe_api = ApiClient(running_api, service_token=SERVICE_TOKEN)
        try:
            return run_dev_agent(
                ticket_id=frontend_task["id"],
                task_spec=_task_spec_for(frontend_task),
                workspace_dir=fe_workspace,
                api=fe_api,
                claude_runner=FixtureClaudeCodeRunner(_FIXTURES_DIR / "e2e_frontend_task"),
                github=github,
                config=config,
                profile=_FRONTEND_PROFILE,
            )
        finally:
            fe_api.close()

    def _run_be() -> DevAgentResult:
        be_api = ApiClient(running_api, service_token=SERVICE_TOKEN)
        try:
            return run_dev_agent(
                ticket_id=backend_task["id"],
                task_spec=_task_spec_for(backend_task),
                workspace_dir=be_workspace,
                api=be_api,
                claude_runner=FixtureClaudeCodeRunner(_FIXTURES_DIR / "e2e_backend_task"),
                github=github,
                config=config,
                profile=_BACKEND_PROFILE,
            )
        finally:
            be_api.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        fe_future = pool.submit(_run_fe)
        be_future = pool.submit(_run_be)
        fe_dev_result = fe_future.result()
        be_dev_result = be_future.result()

    assert fe_dev_result.status == "completed"
    assert be_dev_result.status == "completed"
    assert api.get_ticket(frontend_task["id"])["state"] == "in_review"
    assert api.get_ticket(backend_task["id"])["state"] == "in_review"

    # 5. Review, sequentially - each task gets its own canned diff off the shared
    # FakeGitHubClient (its `.diff` field is swapped between calls).
    monkeypatch.setattr(
        review_module, "route", lambda *a, **k: _FakeRouteResult(_approve_json(), cost_usd=0.002)
    )

    github.diff = _FRONTEND_DIFF
    fe_pr = github.get_pr_for_branch(f"agent/{frontend_task['id']}")
    fe_review = run_review_agent(
        ticket_id=frontend_task["id"],
        task_spec=_task_spec_for(frontend_task),
        pr=fe_pr,
        api=api,
        github=github,
    )
    assert fe_review.verdict == "approve"

    github.diff = _BACKEND_DIFF
    be_pr = github.get_pr_for_branch(f"agent/{backend_task['id']}")
    be_review = run_review_agent(
        ticket_id=backend_task["id"],
        task_spec=_task_spec_for(backend_task),
        pr=be_pr,
        api=api,
        github=github,
    )
    assert be_review.verdict == "approve"

    assert api.get_ticket(frontend_task["id"])["state"] == "in_qa"
    assert api.get_ticket(backend_task["id"])["state"] == "in_qa"

    # 6. QA -> merge queue -> done, for real (no mocked git anywhere in this step).
    api.report_ci_result(frontend_task["id"], conclusion="success")
    api.report_ci_result(backend_task["id"], conclusion="success")

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    merge_result = run_merge_queue(
        api=api, github=github, repo_url=origin_url, workspace_root=scratch, repo=DEFAULT_REPO
    )
    outcomes_by_ticket = {o.ticket_id: o.outcome for o in merge_result.processed}
    assert outcomes_by_ticket[frontend_task["id"]] == "merged"
    assert outcomes_by_ticket[backend_task["id"]] == "merged"
    assert list(scratch.iterdir()) == []  # no orphaned scratch clones

    assert api.get_ticket(frontend_task["id"])["state"] == "done"
    assert api.get_ticket(backend_task["id"])["state"] == "done"

    # AC2: full, real event history for each task - transition/assignment/review/
    # test_result/cost events all present, all written via the public API (this
    # test never imports a DB session or an ORM model - see module docstring).
    fe_event_kinds = {e["kind"] for e in _get_events(running_api, frontend_task["id"])}
    assert {"transition", "assignment", "review", "test_result", "cost"} <= fe_event_kinds

    # AC3: total scenario cost (planner + DM + 2x dev + 2x review, all real
    # agent_runs/cost_ledger rows) stays under the configured cap.
    rollup = api.cost_rollup(idea["id"])
    assert rollup["rollup_usd"] > 0
    assert rollup["rollup_usd"] <= scenario_cost_cap_usd()


def _task_spec_for(ticket: dict[str, object]) -> TaskSpec:
    spec = ticket["spec"]
    return TaskSpec(
        id=ticket["id"],
        title=ticket["title"],
        context=spec.get("context", ""),
        acceptance_criteria=[
            AcceptanceCriterion(**c) for c in spec.get("acceptance_criteria", [])
        ]
        or [AcceptanceCriterion(id="AC-1", description="d", verification="v")],
        complexity=Complexity(spec.get("complexity", "low")),
        budget_usd=ticket["budget_usd"],
        required_skills=spec.get("required_skills", []),
    )
