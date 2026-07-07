"""T-107 / SPEC-106: the merge-queue endpoints, the audit query (AC2), and the
repo-concurrency-limit test at the exact 5-tickets/3-slots cardinality (AC3)."""

from typing import Any

from fastapi.testclient import TestClient
from schemas import DEFAULT_REPO
from sqlalchemy.orm import Session

from api.db.models import TicketState, TicketType
from api.repositories import ticket_repository as repo
from api.services import ticket_service
from api.tenancy import DEFAULT_ORG_ID

from .test_ci_webhook_api import _post_ci_result, _ready_ticket_in_qa
from .test_tickets_api import _complete_via_merge_queue, _create_task


def test_audit_query_is_clean_after_a_real_merge_queue_completion(
    client: TestClient, db_session: Session
) -> None:
    ticket_id = _ready_ticket_in_qa(client)
    assert _complete_via_merge_queue(client, ticket_id).status_code == 200

    violations = ticket_service.tickets_done_without_merge_queue_entry(
        db_session, org_id=DEFAULT_ORG_ID
    )
    assert ticket_id not in violations


def test_audit_query_catches_a_done_ticket_with_no_merge_queue_entry(
    db_session: Session,
) -> None:
    # Fault injection: a `done` ticket that never went through the queue at all —
    # the only way this should happen is a bug, and the audit query must catch it.
    ticket = repo.create_ticket(
        db_session,
        org_id=DEFAULT_ORG_ID,
        ticket_type=TicketType.TASK,
        title="Bypassed the queue",
        parent_id=None,
        spec=None,
        acceptance_criteria=[{"id": "AC-1", "description": "d", "verification": "v"}],
        assignee_agent=None,
        budget_usd=10.0,
        created_by="human:alice",
    )
    ticket.state = TicketState.DONE
    db_session.commit()

    violations = ticket_service.tickets_done_without_merge_queue_entry(
        db_session, org_id=DEFAULT_ORG_ID
    )
    assert ticket.id in violations


def test_merge_queue_conflict_endpoint_bounces_with_failure_report(client: TestClient) -> None:
    ticket_id = _ready_ticket_in_qa(client)
    _post_ci_result(client, {"ticket_id": ticket_id, "conclusion": "success"})

    queued = client.get("/merge-queue", params={"repo": DEFAULT_REPO}).json()["items"]
    entry = next(e for e in queued if e["ticket_id"] == ticket_id)

    response = client.post(
        f"/merge-queue/{entry['id']}/conflict",
        json={"actor": "system:merge-queue", "conflicting_paths": ["app.py"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "bounced"
    assert response.json()["bounce_count"] == 1

    events = client.get(f"/tickets/{ticket_id}/events").json()["items"]
    test_result_events = [e for e in events if e["kind"] == "test_result"]
    assert len(test_result_events) == 1
    report = test_result_events[0]["payload"]["failure_report"]
    assert report["failing_suite"] == "conflict"
    assert report["suspect_files"] == ["app.py"]


def test_repo_concurrency_limit_defers_two_of_five_ready_tickets(client: TestClient) -> None:
    """AC3: capability_registry.yaml's repo_concurrency_limit is 3 — with 5 ready
    tasks on the same (default) repo assigned across DIFFERENT profiles (so no
    single profile's own max_parallel is what blocks anything), exactly 3 reach
    in_progress and 2 are refused specifically for repo concurrency."""
    ticket_ids = [_create_task(client)["id"] for _ in range(5)]
    # 4 distinct profiles from capability_registry.yaml, each with its own
    # max_parallel headroom — the repo-wide limit (3) binds first, not any one
    # profile's own capacity.
    profiles = ["dev-generalist", "dev-frontend", "dev-backend", "dev-devops", "dev-generalist"]

    def _assign(ticket_id: str, profile: str) -> Any:
        return client.post(
            f"/tickets/{ticket_id}/transition",
            json={
                "to_state": "in_progress",
                "actor": "agent:delivery-manager",
                "assignee_agent": profile,
            },
        )

    results = [_assign(tid, profile) for tid, profile in zip(ticket_ids, profiles, strict=True)]
    succeeded = [r for r in results if r.status_code == 200]
    refused = [r for r in results if r.status_code == 409]

    assert len(succeeded) == 3
    assert len(refused) == 2
    for r in refused:
        assert "concurrency limit" in r.json()["detail"]
