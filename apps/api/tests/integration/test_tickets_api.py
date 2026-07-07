from typing import Any

from fastapi.testclient import TestClient
from schemas import DEFAULT_REPO


def _create_task(
    client: TestClient,
    *,
    budget_usd: float | None = 100.0,
    acceptance_criteria: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    payload = {
        "type": "task",
        "title": "Do the thing",
        "created_by": "human:alice",
        "budget_usd": budget_usd,
        "acceptance_criteria": (
            acceptance_criteria
            if acceptance_criteria is not None
            else [{"id": "AC-1", "description": "d", "verification": "v"}]
        ),
    }
    response = client.post("/tickets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def _transition(
    client: TestClient, ticket_id: str, to_state: str, actor: str = "human:alice"
) -> Any:
    body = {"to_state": to_state, "actor": actor}
    return client.post(f"/tickets/{ticket_id}/transition", json=body)


def _dev_login(client: TestClient, email: str, role: str) -> str:
    response = client.post("/auth/dev-login", json={"email": email, "role": role})
    assert response.status_code == 200, response.text
    return response.json()["token"]  # type: ignore[no-any-return]


def _complete_via_merge_queue(
    client: TestClient, ticket_id: str, *, repo: str = DEFAULT_REPO
) -> Any:
    """SPEC-106: CI-green only enqueues a ticket now — this drives it the rest of
    the way to `done` through the real merge-queue endpoints, standing in for
    apps/orchestrator's merge_queue.py in tests that don't need the real git/gh
    mechanics, just the end state."""
    ci_response = client.post(
        "/webhooks/ci-result", json={"ticket_id": ticket_id, "conclusion": "success"}
    )
    assert ci_response.status_code == 200, ci_response.text
    queued = client.get("/merge-queue", params={"repo": repo}).json()["items"]
    entry = next(e for e in queued if e["ticket_id"] == ticket_id)
    return client.post(
        f"/merge-queue/{entry['id']}/merge", json={"actor": "system:merge-queue"}
    )


def test_create_task_with_empty_acceptance_criteria_fails_422(client: TestClient) -> None:
    response = client.post(
        "/tickets",
        json={
            "type": "task",
            "title": "x",
            "created_by": "human:alice",
            "budget_usd": 10,
            "acceptance_criteria": [],
        },
    )

    assert response.status_code == 422


def test_get_and_list_tickets(client: TestClient) -> None:
    created = _create_task(client)

    get_response = client.get(f"/tickets/{created['id']}")
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["id"] == created["id"]
    assert body["state"] == "ready"
    assert body["recent_events"] == []

    list_response = client.get("/tickets", params={"type": "task", "state": "ready"})
    assert list_response.status_code == 200
    listed = list_response.json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == created["id"]

    assert client.get("/tickets/does-not-exist").status_code == 404


def test_ready_to_in_progress_to_in_review_to_in_qa_to_done_writes_one_event_each(
    client: TestClient,
) -> None:
    ticket = _create_task(client)
    ticket_id = ticket["id"]

    assert _transition(client, ticket_id, "in_progress").status_code == 200
    assert _transition(client, ticket_id, "in_review").status_code == 200
    assert _transition(client, ticket_id, "in_qa").status_code == 200
    done_response = _complete_via_merge_queue(client, ticket_id)
    assert done_response.status_code == 200, done_response.text
    assert done_response.json()["state"] == "done"

    events = client.get(f"/tickets/{ticket_id}/events").json()
    transition_events = [e for e in events["items"] if e["kind"] == "transition"]
    assert len(transition_events) == 4
    assert all(not e["payload"].get("rejected") for e in transition_events)


def test_in_progress_can_no_longer_skip_the_review_gate(client: TestClient) -> None:
    ticket = _create_task(client)
    ticket_id = ticket["id"]
    _transition(client, ticket_id, "in_progress")

    response = _transition(client, ticket_id, "in_qa")
    assert response.status_code == 409

    events = client.get(f"/tickets/{ticket_id}/events").json()
    rejected = [e for e in events["items"] if e["payload"].get("rejected")]
    assert len(rejected) == 1


def test_in_qa_to_done_refused_once_bounce_count_hits_three(client: TestClient) -> None:
    ticket = _create_task(client)
    ticket_id = ticket["id"]
    _transition(client, ticket_id, "in_progress")

    for _ in range(3):
        assert _transition(client, ticket_id, "in_review").status_code == 200
        assert _transition(client, ticket_id, "in_qa").status_code == 200
        assert _transition(client, ticket_id, "bounced").status_code == 200
        assert _transition(client, ticket_id, "in_progress").status_code == 200

    assert _transition(client, ticket_id, "in_review").status_code == 200
    assert _transition(client, ticket_id, "in_qa").status_code == 200
    done_response = _transition(client, ticket_id, "done")
    assert done_response.status_code == 409


def test_fourth_bounce_attempt_refused_and_ticket_auto_escalates(client: TestClient) -> None:
    ticket = _create_task(client)
    ticket_id = ticket["id"]
    _transition(client, ticket_id, "in_progress")

    for _ in range(3):
        assert _transition(client, ticket_id, "in_review").status_code == 200
        assert _transition(client, ticket_id, "in_qa").status_code == 200
        assert _transition(client, ticket_id, "bounced").status_code == 200
        assert _transition(client, ticket_id, "in_progress").status_code == 200

    assert _transition(client, ticket_id, "in_review").status_code == 200
    assert _transition(client, ticket_id, "in_qa").status_code == 200
    fourth_bounce = _transition(client, ticket_id, "bounced")
    assert fourth_bounce.status_code == 409

    ticket_after = client.get(f"/tickets/{ticket_id}").json()
    assert ticket_after["state"] == "escalated"
    assert ticket_after["bounce_count"] == 3


def test_review_bounce_and_qa_bounce_share_one_counter_and_auto_escalate(
    client: TestClient,
) -> None:
    """SPEC/docs/03-state-machine.md: "a ticket gets 3 total attempts, not 3 per gate" —
    interleave a review-block bounce with QA-fail bounces and confirm the 4th bounce
    from either gate is refused and auto-escalates."""
    ticket = _create_task(client)
    ticket_id = ticket["id"]
    _transition(client, ticket_id, "in_progress")

    # Bounce 1: blocked at review, never reaches QA.
    assert _transition(client, ticket_id, "in_review").status_code == 200
    assert _transition(client, ticket_id, "bounced").status_code == 200
    assert _transition(client, ticket_id, "in_progress").status_code == 200

    # Bounces 2 and 3: fail at QA.
    for _ in range(2):
        assert _transition(client, ticket_id, "in_review").status_code == 200
        assert _transition(client, ticket_id, "in_qa").status_code == 200
        assert _transition(client, ticket_id, "bounced").status_code == 200
        assert _transition(client, ticket_id, "in_progress").status_code == 200

    ticket_after_three = client.get(f"/tickets/{ticket_id}").json()
    assert ticket_after_three["bounce_count"] == 3

    # A 4th bounce, from either gate, is refused and auto-escalates the shared counter.
    assert _transition(client, ticket_id, "in_review").status_code == 200
    fourth_bounce = _transition(client, ticket_id, "bounced")
    assert fourth_bounce.status_code == 409

    ticket_after = client.get(f"/tickets/{ticket_id}").json()
    assert ticket_after["state"] == "escalated"
    assert ticket_after["bounce_count"] == 3


def test_events_endpoint_is_append_only(client: TestClient) -> None:
    ticket = _create_task(client)
    ticket_id = ticket["id"]

    assert client.put(f"/tickets/{ticket_id}/events", json={}).status_code == 405
    assert client.delete(f"/tickets/{ticket_id}/events").status_code == 405


def test_approve_by_non_approver_returns_403_and_approver_succeeds(client: TestClient) -> None:
    ticket = _create_task(client)
    ticket_id = ticket["id"]

    viewer_token = _dev_login(client, "bob@example.com", "viewer")
    forbidden = client.post(
        f"/tickets/{ticket_id}/approve",
        json={"gate": "budget", "decision": "approved"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert forbidden.status_code == 403

    approver_token = _dev_login(client, "carol@example.com", "approver")
    approved = client.post(
        f"/tickets/{ticket_id}/approve",
        json={"gate": "budget", "decision": "approved", "note": "looks good"},
        headers={"Authorization": f"Bearer {approver_token}"},
    )
    assert approved.status_code == 200
    assert approved.json()["decided_by"] == "human:carol@example.com"
