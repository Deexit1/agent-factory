"""T-206 (SPEC-206 AC4): "Funnel dashboard reproduces a seeded fixture cohort exactly."
Six orgs seeded with real, staggered progress (each org accumulates one more stage than
the last) inside a fixed, synthetic cohort window far from "now" — deliberately
excluding the db_session fixture's own seeded default org (created at real `now`) so
the expected counts are exact, not "6 plus whatever else exists"."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.db.models import MergeQueueStatus, RepoMode, TicketType
from api.repositories import (
    org_repository,
    provider_key_repository,
    repo_repository,
    tos_repository,
)
from api.repositories import ticket_repository as repo
from api.tos import CURRENT_TOS_VERSION

from .conftest import _auth
from .test_tickets_api import _dev_login

_COHORT_START = datetime(2020, 1, 1, tzinfo=UTC)
_COHORT_END = _COHORT_START + timedelta(days=1)


def _set_created_at(session: Session, *, org_id: str, ts: datetime) -> None:
    session.execute(
        text("UPDATE orgs SET created_at = :ts WHERE id = :id"), {"ts": ts, "id": org_id}
    )


def _seed_cohort(session: Session) -> None:
    orgs = [org_repository.create_org(session, name=f"Funnel Org {c}") for c in "ABCDEF"]
    for i, org in enumerate(orgs):
        _set_created_at(session, org_id=org.id, ts=_COHORT_START + timedelta(hours=i))
    session.flush()

    org_a, org_b, org_c, org_d, org_e, org_f = orgs

    # B..F: ToS accepted
    for org in (org_b, org_c, org_d, org_e, org_f):
        tos_repository.record_tos_acceptance(
            session,
            org_id=org.id,
            accepted_by="owner@example.com",
            tos_version=CURRENT_TOS_VERSION,
            accepted_at=datetime.now(UTC),
        )

    # C..F: BYOK key added
    for org in (org_c, org_d, org_e, org_f):
        provider_key_repository.create_provider_key(
            session,
            org_id=org.id,
            provider="anthropic",
            last4="1234",
            created_by="owner@example.com",
        )

    # D..F: repo connected
    for org in (org_d, org_e, org_f):
        repo_repository.create_repo(
            session,
            org_id=org.id,
            mode=RepoMode.PROVISIONED,
            github_installation_id=999,
            created_by="owner@example.com",
        )

    # E..F: first idea ticket
    idea_tickets = {}
    for org in (org_e, org_f):
        ticket = repo.create_ticket(
            session,
            org_id=org.id,
            ticket_type=TicketType.IDEA,
            title="First idea",
            parent_id=None,
            spec=None,
            acceptance_criteria=[],
            assignee_agent=None,
            budget_usd=50.0,
            created_by="human:owner",
        )
        idea_tickets[org.id] = ticket

    # F only: first PR merged
    merge_entry = repo.create_merge_queue_entry(
        session, org_id=org_f.id, ticket_id=idea_tickets[org_f.id].id, repo="acme/repo"
    )
    repo.resolve_merge_queue_entry(session, merge_entry, status=MergeQueueStatus.MERGED)

    session.commit()
    assert org_a.id  # keep org_a referenced (created-only baseline, zero elsewhere)


def test_funnel_dashboard_reproduces_the_seeded_cohort_exactly(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_cohort(db_session)

    monkeypatch.setenv("PLATFORM_STAFF_EMAILS", "funnel-staff@example.com")
    staff_token = _dev_login(client, "funnel-staff@example.com", "viewer")

    response = client.get(
        "/dashboard/funnel",
        params={"start": _COHORT_START.isoformat(), "end": _COHORT_END.isoformat()},
        headers=_auth(staff_token),
    )
    assert response.status_code == 200, response.text
    stages = {row["stage"]: row["org_count"] for row in response.json()["stages"]}

    assert stages == {
        "signup": 6,
        "tos_accepted": 5,
        "key_added": 4,
        "repo_connected": 3,
        "first_idea_created": 2,
        "first_pr_merged": 1,
    }


def test_funnel_dashboard_is_staff_only(client: TestClient) -> None:
    owner_token = _dev_login(client, "funnel-owner@example.com", "owner")
    response = client.get(
        "/dashboard/funnel",
        params={"start": _COHORT_START.isoformat(), "end": _COHORT_END.isoformat()},
        headers=_auth(owner_token),
    )
    assert response.status_code == 403
