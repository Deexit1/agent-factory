import hashlib
import hmac
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from .test_tickets_api import _create_task, _transition

PYTEST_FAILURE_LOG = """\
FAILED tests/test_widget.py::test_widget_returns_200 - assert 500 == 200
"""


def _ready_ticket_in_qa(client: TestClient) -> str:
    ticket = _create_task(client)
    ticket_id: str = ticket["id"]
    assert _transition(client, ticket_id, "in_progress").status_code == 200
    assert _transition(client, ticket_id, "in_qa").status_code == 200
    return ticket_id


def _post_ci_result(
    client: TestClient, payload: dict[str, object], *, secret: str | None = None
) -> httpx.Response:
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if secret is not None:
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Hub-Signature-256"] = f"sha256={signature}"
    return client.post("/webhooks/ci-result", content=body, headers=headers)


def test_green_pipeline_transitions_ticket_to_done(client: TestClient) -> None:
    ticket_id = _ready_ticket_in_qa(client)

    response = _post_ci_result(client, {"ticket_id": ticket_id, "conclusion": "success"})

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "done"


def test_red_pipeline_bounces_with_failure_report_matching_ci_log(client: TestClient) -> None:
    ticket_id = _ready_ticket_in_qa(client)

    response = _post_ci_result(
        client,
        {
            "ticket_id": ticket_id,
            "conclusion": "failure",
            "suite": "unit",
            "raw_log": PYTEST_FAILURE_LOG,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "bounced"
    assert response.json()["bounce_count"] == 1

    events = client.get(f"/tickets/{ticket_id}/events").json()["items"]
    test_result_events = [e for e in events if e["kind"] == "test_result"]
    assert len(test_result_events) == 1
    report = test_result_events[0]["payload"]["failure_report"]
    assert report["failing_tests"] == ["tests/test_widget.py::test_widget_returns_200"]
    assert report["attempt_no"] == 1


def test_fourth_consecutive_red_pipeline_escalates_instead_of_bouncing(
    client: TestClient,
) -> None:
    ticket_id = _ready_ticket_in_qa(client)

    for expected_bounce_count in (1, 2, 3):
        response = _post_ci_result(
            client,
            {"ticket_id": ticket_id, "conclusion": "failure", "raw_log": PYTEST_FAILURE_LOG},
        )
        assert response.status_code == 200, response.text
        assert response.json()["state"] == "bounced"
        assert response.json()["bounce_count"] == expected_bounce_count
        assert _transition(client, ticket_id, "in_progress").status_code == 200
        assert _transition(client, ticket_id, "in_qa").status_code == 200

    response = _post_ci_result(
        client,
        {"ticket_id": ticket_id, "conclusion": "failure", "raw_log": PYTEST_FAILURE_LOG},
    )

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "escalated"
    assert response.json()["bounce_count"] == 3


def test_ci_result_404_for_missing_ticket(client: TestClient) -> None:
    response = _post_ci_result(client, {"ticket_id": "does-not-exist", "conclusion": "success"})
    assert response.status_code == 404


def test_ci_result_409_when_ticket_not_in_qa(client: TestClient) -> None:
    ticket = _create_task(client)

    response = _post_ci_result(client, {"ticket_id": ticket["id"], "conclusion": "success"})

    assert response.status_code == 409


def test_ci_result_rejects_missing_or_wrong_signature_when_secret_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CI_WEBHOOK_SECRET", "s3cr3t")
    ticket_id = _ready_ticket_in_qa(client)

    unsigned = _post_ci_result(client, {"ticket_id": ticket_id, "conclusion": "success"})
    assert unsigned.status_code == 401

    wrong_secret = _post_ci_result(
        client, {"ticket_id": ticket_id, "conclusion": "success"}, secret="wrong"
    )
    assert wrong_secret.status_code == 401

    correctly_signed = _post_ci_result(
        client, {"ticket_id": ticket_id, "conclusion": "success"}, secret="s3cr3t"
    )
    assert correctly_signed.status_code == 200
