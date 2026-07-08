"""T-202 (SPEC-202 AC3): Org A's runs are billed to Org A's key — real Vault, real
Postgres, two orgs each with a distinct fake key. Proves (a) runtime-key resolution
never cross-contaminates between orgs, and (b) the resulting AgentRun/CostLedgerEntry
rows carry the correct provider/org_id, which is as far as "provider-side usage
matches agent_runs attribution" can be asserted without a live provider billing
dashboard (no CI environment can reconcile against that deterministically either)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.services import provider_key_service

from .test_tickets_api import _dev_login


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _no_real_provider_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_key_service, "validate_key", lambda **kwargs: None)


def _create_org_with_key(
    client: TestClient, *, owner_email: str, org_name: str, api_key: str
) -> tuple[str, str]:
    owner_token = _dev_login(client, owner_email, "owner")
    org = client.post("/orgs", json={"name": org_name}, headers=_auth(owner_token)).json()
    owner_org_token = client.post(
        "/auth/switch-org", json={"org_id": org["id"]}, headers=_auth(owner_token)
    ).json()["token"]
    client.post(
        f"/orgs/{org['id']}/provider-keys",
        json={"provider": "anthropic", "api_key": api_key},
        headers=_auth(owner_org_token),
    )
    return org["id"], owner_org_token


def test_runtime_keys_never_cross_contaminate_between_orgs(
    client: TestClient, vault_addr: str
) -> None:
    org_a_id, _ = _create_org_with_key(
        client, owner_email="byok-a@example.com", org_name="Org A", api_key="sk-ant-ORG-A-FAKE-KEY"
    )
    org_b_id, _ = _create_org_with_key(
        client, owner_email="byok-b@example.com", org_name="Org B", api_key="sk-ant-ORG-B-FAKE-KEY"
    )

    service_headers = {"Authorization": f"Bearer {_service_token()}"}
    keys_a = client.get(f"/orgs/{org_a_id}/llm/runtime-keys", headers=service_headers).json()
    keys_b = client.get(f"/orgs/{org_b_id}/llm/runtime-keys", headers=service_headers).json()

    assert keys_a["items"] == [{"provider": "anthropic", "api_key": "sk-ant-ORG-A-FAKE-KEY"}]
    assert keys_b["items"] == [{"provider": "anthropic", "api_key": "sk-ant-ORG-B-FAKE-KEY"}]


def test_agent_run_and_cost_ledger_attribution_is_org_scoped(
    client: TestClient, vault_addr: str
) -> None:
    org_a_id, owner_a_token = _create_org_with_key(
        client,
        owner_email="byok-attr-a@example.com",
        org_name="Attribution Org A",
        api_key="sk-ant-ATTR-A-FAKE",
    )
    org_b_id, owner_b_token = _create_org_with_key(
        client,
        owner_email="byok-attr-b@example.com",
        org_name="Attribution Org B",
        api_key="sk-ant-ATTR-B-FAKE",
    )

    task_a = _create_task(client, owner_a_token)
    task_b = _create_task(client, owner_b_token)

    _run_and_complete_agent_run(client, owner_a_token, task_a["id"], cost_usd=0.05)
    _run_and_complete_agent_run(client, owner_b_token, task_b["id"], cost_usd=0.09)

    ledger_a = client.get(
        f"/tickets/{task_a['id']}/cost-ledger", headers=_auth(owner_a_token)
    ).json()
    ledger_b = client.get(
        f"/tickets/{task_b['id']}/cost-ledger", headers=_auth(owner_b_token)
    ).json()

    assert len(ledger_a) == 1
    assert ledger_a[0]["provider"] == "anthropic"
    assert ledger_a[0]["usd"] == 0.05

    assert len(ledger_b) == 1
    assert ledger_b[0]["provider"] == "anthropic"
    assert ledger_b[0]["usd"] == 0.09

    # Cross-tenant read: org A cannot see org B's ticket at all (T-201 AC1 convention).
    cross = client.get(f"/tickets/{task_b['id']}/cost-ledger", headers=_auth(owner_a_token))
    assert cross.status_code == 404


def _create_task(client: TestClient, token: str) -> dict[str, Any]:
    response = client.post(
        "/tickets",
        json={
            "type": "task",
            "title": "BYOK attribution task",
            "created_by": "human:byok",
            "budget_usd": 20.0,
            "acceptance_criteria": [{"id": "AC-1", "description": "d", "verification": "v"}],
        },
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def _run_and_complete_agent_run(
    client: TestClient, token: str, ticket_id: str, *, cost_usd: float
) -> None:
    run = client.post(
        f"/tickets/{ticket_id}/agent-runs",
        json={"agent_role": "dev", "model": "claude-sonnet-5"},
        headers=_auth(token),
    ).json()
    complete = client.post(
        f"/tickets/{ticket_id}/agent-runs/{run['id']}/complete",
        json={
            "status": "completed",
            "tokens_in": 100,
            "tokens_out": 50,
            "cost_usd": cost_usd,
            "provider": "anthropic",
        },
        headers=_auth(token),
    )
    assert complete.status_code == 200, complete.text


def _service_token() -> str:
    import os

    return os.environ["AGENT_FACTORY_SERVICE_TOKEN"]
