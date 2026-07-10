"""T-211: the exact gap disclosed three times before (T-201/T-202/T-206) and
explicitly, deliberately left unclosed by test_e2e_onboarding_flow.py's own module
docstring — "the orchestrator's dev-agent pipeline ... cannot run against a freshly
created, non-default org today." This proves it now can, for the Planner stage:
the service token, scoped via the new X-Org-Id header (api.auth.get_actor_context),
creates and plans an idea ticket in a brand-new org it was never a member of and
never logged into as a human — only apps/api's org resolution ever locked this down;
get_runtime_keys/resolve_dispatch were already correctly multi-org (see
apps/api/tests/integration/test_byok_attribution.py).
"""

import json
import urllib.request

import pytest

from orchestrator.agents import planner as planner_module
from orchestrator.agents.planner import run_planner_agent
from orchestrator.api_client import ApiClient

from .conftest import SERVICE_TOKEN


class _FakeRouteResult:
    def __init__(self, text: str) -> None:
        self.text = text
        self.model = "claude-opus-4-8"
        self.provider = "anthropic"
        self.tokens_in = 500
        self.tokens_out = 300
        self.cost_usd = 0.03


def _post(url: str, *, token: str | None = None, body: dict[str, object] | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url, method="POST", headers=headers, data=json.dumps(body or {}).encode()
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())  # type: ignore[no-any-return]


def _get(url: str, *, token: str) -> dict:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())  # type: ignore[no-any-return]


def _create_brand_new_org(running_api: str) -> str:
    """Mirrors CreateOrgStep.tsx's real flow exactly: a human dev-logs in (into the
    seeded default org, migration-seeded so it always exists), then creates their OWN
    org — the same two real API calls a real user's browser makes. This org has no
    relationship whatsoever to the service token beyond what T-211 now allows."""
    login = _post(
        f"{running_api}/auth/dev-login",
        body={"email": "multi-org-owner@example.com", "role": "owner", "org_id": "default"},
    )
    human_token = login["token"]

    tos = _get(f"{running_api}/tos", token=human_token)
    org = _post(
        f"{running_api}/orgs",
        token=human_token,
        body={"name": "A Brand New Org", "tos_version": tos["version"]},
    )
    return org["id"]  # type: ignore[no-any-return]


def test_planner_agent_runs_for_a_brand_new_non_default_org(
    running_api: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    new_org_id = _create_brand_new_org(running_api)
    assert new_org_id != "default"

    # The service token, scoped to the new org via X-Org-Id — never a human member,
    # never dev-logged-in to it, exactly like the real orchestrator would operate.
    api = ApiClient(running_api, service_token=SERVICE_TOKEN, org_id=new_org_id)

    idea = api.create_ticket(
        ticket_type="idea",
        title="Automate the new org's onboarding",
        created_by="human:multi-org-owner@example.com",
        budget_usd=100.0,
    )
    assert idea["org_id"] == new_org_id
    api.transition(idea["id"], to_state="planning", actor="human:multi-org-owner@example.com")

    plan_json = json.dumps(
        {
            "epics": [
                {"id": "epic-1", "title": "Foundations", "description": "d", "budget_usd": 60.0}
            ],
            "tasks": [
                {
                    "id": "task-1",
                    "title": "Add onboarding endpoint",
                    "context": "ctx",
                    "acceptance_criteria": [
                        {"id": "AC-1", "description": "d", "verification": "v"}
                    ],
                    "complexity": "low",
                    "budget_usd": 20.0,
                    "depends_on": [],
                    "estimate_days": 0.5,
                    "epic_id": "epic-1",
                }
            ],
        }
    )
    monkeypatch.setattr(planner_module, "route", lambda *a, **k: _FakeRouteResult(plan_json))

    result = run_planner_agent(
        ticket_id=idea["id"],
        idea_title=idea["title"],
        idea_description="",
        idea_budget_usd=100.0,
        api=api,
    )

    assert result.status == "planned"
    descendants = api.descendants(idea["id"])
    epics = [d for d in descendants if d["type"] == "epic"]
    tasks = [d for d in descendants if d["type"] == "task"]
    assert len(epics) == 1
    assert len(tasks) == 1
    assert all(d["org_id"] == new_org_id for d in descendants)


def test_a_default_scoped_client_cannot_see_the_new_orgs_ticket(running_api: str) -> None:
    """Proves the scoping is real isolation, not cosmetic — the same service secret,
    without X-Org-Id pointed at the new org, still only ever sees DEFAULT_ORG_ID's
    tickets, exactly as before T-211."""
    new_org_id = _create_brand_new_org(running_api)
    scoped_api = ApiClient(running_api, service_token=SERVICE_TOKEN, org_id=new_org_id)
    idea = scoped_api.create_ticket(
        ticket_type="idea",
        title="Should not be visible to the default-scoped client",
        created_by="human:multi-org-owner@example.com",
        budget_usd=50.0,
    )

    default_api = ApiClient(running_api, service_token=SERVICE_TOKEN)
    import httpx

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        default_api.get_ticket(idea["id"])
    assert exc_info.value.response.status_code == 404
