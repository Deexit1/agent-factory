"""T-205 (SPEC-205 "In scope": free tier hard caps). Same shape as T-201's
test_org_quota.py: a free-plan org that has used up its included agent-run-minutes for
the month is refused a new ready->in_progress transition, leaving the task `ready` with
a quota-rejection event — real end-to-end, not a mocked usage sum. Paid-tier orgs never
hit this guard (they bill overage instead, see test_billing_metering_job.py)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.billing_plans import PLANS
from api.db.models import AgentRun, AgentRunStatus, Org
from api.services import billing_service

from .conftest import _auth
from .test_tickets_api import _dev_login


def _owner_org_token(client: TestClient, email: str, org_name: str) -> tuple[str, str]:
    owner_token = _dev_login(client, email, "owner")
    org = client.post("/orgs", json={"name": org_name}, headers=_auth(owner_token)).json()
    org_id = org["id"]
    owner_org_token = client.post(
        "/auth/switch-org", json={"org_id": org_id}, headers=_auth(owner_token)
    ).json()["token"]
    return org_id, owner_org_token


def _create_task_as(client: TestClient, token: str, title: str) -> dict[str, Any]:
    response = client.post(
        "/tickets",
        headers=_auth(token),
        json={
            "type": "task",
            "title": title,
            "created_by": "human:alice",
            "budget_usd": 20.0,
            "acceptance_criteria": [{"id": "AC-1", "description": "d", "verification": "v"}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def _seed_over_the_free_tier_agent_run_minutes(
    db_session: Session, *, org_id: str, ticket_id: str
) -> None:
    over_included = PLANS["free"].included_agent_run_minutes + 10
    started_at = datetime.now(UTC) - timedelta(minutes=over_included + 5)
    db_session.add(
        AgentRun(
            org_id=org_id,
            ticket_id=ticket_id,
            agent_role="dev",
            model="claude-sonnet-5",
            started_at=started_at,
            ended_at=started_at + timedelta(minutes=over_included),
            status=AgentRunStatus.COMPLETED,
            provider="anthropic",
        )
    )
    db_session.commit()


def test_free_tier_org_over_its_usage_cap_is_refused_new_work(
    client: TestClient, db_session: Session
) -> None:
    org_id, owner_token = _owner_org_token(client, "owner-freecap1@example.com", "Free cap org 1")
    org = db_session.get(Org, org_id)
    assert org is not None
    assert org.plan == "free"

    burner_task = _create_task_as(client, owner_token, "Burner task")
    _seed_over_the_free_tier_agent_run_minutes(
        db_session, org_id=org_id, ticket_id=burner_task["id"]
    )

    task = _create_task_as(client, owner_token, "New task")
    response = client.post(
        f"/tickets/{task['id']}/transition",
        json={"to_state": "in_progress", "actor": "human:alice"},
        headers=_auth(owner_token),
    )

    assert response.status_code == 409, response.text
    assert "usage" in response.json()["detail"].lower()

    ticket_after = client.get(f"/tickets/{task['id']}", headers=_auth(owner_token)).json()
    assert ticket_after["state"] == "ready"

    events = client.get(
        f"/tickets/{task['id']}/events?limit=100", headers=_auth(owner_token)
    ).json()["items"]
    rejected = [e for e in events if e["kind"] == "transition" and e["payload"].get("rejected")]
    assert len(rejected) == 1
    assert "usage" in rejected[0]["payload"]["reason"].lower()


def test_paid_tier_org_over_the_free_allowance_is_unaffected(
    client: TestClient, db_session: Session
) -> None:
    """Overage on a paid plan is billed (test_billing_metering_job.py), never a hard
    block — _org_over_usage_cap only ever applies to plan == "free"."""
    org_id, owner_token = _owner_org_token(client, "owner-freecap2@example.com", "Free cap org 2")

    billing_service.set_plan(db_session, org_id, "starter")
    db_session.commit()

    burner_task = _create_task_as(client, owner_token, "Burner task")
    _seed_over_the_free_tier_agent_run_minutes(
        db_session, org_id=org_id, ticket_id=burner_task["id"]
    )

    task = _create_task_as(client, owner_token, "New task")
    response = client.post(
        f"/tickets/{task['id']}/transition",
        json={"to_state": "in_progress", "actor": "human:alice"},
        headers=_auth(owner_token),
    )

    assert response.status_code == 200, response.text
