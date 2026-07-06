"""T-106 / SPEC-105: the in_review -> in_qa/bounced gates enforced in apps/api
(real actor check instead of the previous no-op pass-through), the bounced -> in_qa
human override, and the shared bounce_count between a review-block and a QA-fail."""

from fastapi.testclient import TestClient

from .test_ci_webhook_api import PYTEST_FAILURE_LOG, _post_ci_result
from .test_tickets_api import _create_task, _dev_login, _transition


def _ready_ticket_in_review(client: TestClient) -> str:
    ticket = _create_task(client)
    ticket_id: str = ticket["id"]
    assert _transition(client, ticket_id, "in_progress").status_code == 200
    assert _transition(client, ticket_id, "in_review").status_code == 200
    return ticket_id


def test_in_review_to_in_qa_refused_for_non_review_non_human_actor(client: TestClient) -> None:
    ticket_id = _ready_ticket_in_review(client)

    response = _transition(client, ticket_id, "in_qa", actor="agent:dev-1")
    assert response.status_code == 409
    assert "review agent or a human" in response.json()["detail"]

    assert _transition(client, ticket_id, "in_qa", actor="agent:review-1").status_code == 200


def test_bounced_review_can_be_overridden_by_human_with_approval_row(client: TestClient) -> None:
    ticket_id = _ready_ticket_in_review(client)

    response = _transition(client, ticket_id, "bounced", actor="agent:review-1")
    assert response.status_code == 200, response.text
    assert response.json()["bounce_count"] == 1
    assert response.json()["state"] == "bounced"

    # An agent can't perform the override itself...
    denied = _transition(client, ticket_id, "in_qa", actor="agent:review-1")
    assert denied.status_code == 409

    # ...only a human can, and it's recorded as a review-gate approval.
    approver_token = _dev_login(client, "approver-review@example.com", "approver")
    approval = client.post(
        f"/tickets/{ticket_id}/approve",
        json={"gate": "review", "decision": "approved"},
        headers={"Authorization": f"Bearer {approver_token}"},
    )
    assert approval.status_code == 200, approval.text
    assert approval.json()["gate"] == "review"

    override = _transition(client, ticket_id, "in_qa", actor="human:alice")
    assert override.status_code == 200, override.text
    assert override.json()["state"] == "in_qa"
    assert override.json()["bounce_count"] == 1


def test_review_bounce_then_qa_bounce_share_the_bounce_counter(client: TestClient) -> None:
    ticket_id = _ready_ticket_in_review(client)

    reviewed = _transition(client, ticket_id, "bounced", actor="agent:review-1")
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["bounce_count"] == 1

    assert _transition(client, ticket_id, "in_progress").status_code == 200
    assert _transition(client, ticket_id, "in_review").status_code == 200
    assert _transition(client, ticket_id, "in_qa", actor="agent:review-1").status_code == 200

    ci_response = _post_ci_result(
        client,
        {
            "ticket_id": ticket_id,
            "conclusion": "failure",
            "suite": "unit",
            "raw_log": PYTEST_FAILURE_LOG,
        },
    )
    assert ci_response.status_code == 200, ci_response.text
    assert ci_response.json()["state"] == "bounced"
    assert ci_response.json()["bounce_count"] == 2
