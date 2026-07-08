"""T-205 (SPEC-205): the billing router's real auth gating (owner-only plan changes,
member-only reads, cross-org 404s — same conventions test_egress_router.py already
established) plus the real Razorpay webhook signature verification path."""

import hashlib
import hmac
import json

import httpx
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.db.models import Org

from .conftest import _auth
from .test_tickets_api import _dev_login

_BASE = "https://api.razorpay.com/v1"


def _owner_org_token(client: TestClient, email: str, org_name: str) -> tuple[str, str]:
    owner_token = _dev_login(client, email, "owner")
    org = client.post("/orgs", json={"name": org_name}, headers=_auth(owner_token)).json()
    org_id = org["id"]
    owner_org_token = client.post(
        "/auth/switch-org", json={"org_id": org_id}, headers=_auth(owner_token)
    ).json()["token"]
    return org_id, owner_org_token


def test_get_billing_defaults_to_the_free_plan(client: TestClient) -> None:
    org_id, owner_token = _owner_org_token(client, "owner-billing1@example.com", "Billing org 1")

    response = client.get(f"/orgs/{org_id}/billing", headers=_auth(owner_token))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan"] == "free"
    assert body["billing_status"] == "active"


def test_non_owner_cannot_change_the_plan(client: TestClient) -> None:
    org_id, owner_token = _owner_org_token(client, "owner-billing2@example.com", "Billing org 2")
    member_token = _dev_login(client, "member-billing2@example.com", "member")
    client.post(
        f"/orgs/{org_id}/invites",
        json={"email": "member-billing2@example.com", "role": "member"},
        headers=_auth(owner_token),
    )

    response = client.post(
        f"/orgs/{org_id}/billing/plan", json={"plan": "starter"}, headers=_auth(member_token)
    )

    assert response.status_code in (403, 404)


def test_cross_org_billing_read_is_404_not_403(client: TestClient) -> None:
    org_a, _owner_a = _owner_org_token(client, "owner-billing3a@example.com", "Billing org 3a")
    _org_b, owner_b = _owner_org_token(client, "owner-billing3b@example.com", "Billing org 3b")

    response = client.get(f"/orgs/{org_a}/billing", headers=_auth(owner_b))

    assert response.status_code == 404


def test_set_plan_downgrade_defers_until_period_end(client: TestClient) -> None:
    org_id, owner_token = _owner_org_token(client, "owner-billing4@example.com", "Billing org 4")
    client.post(f"/orgs/{org_id}/billing/plan", json={"plan": "team"}, headers=_auth(owner_token))

    response = client.post(
        f"/orgs/{org_id}/billing/plan", json={"plan": "starter"}, headers=_auth(owner_token)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan"] == "team"  # unchanged immediately
    assert body["pending_plan"] == "starter"


def test_unknown_plan_is_rejected(client: TestClient) -> None:
    org_id, owner_token = _owner_org_token(client, "owner-billing5@example.com", "Billing org 5")

    response = client.post(
        f"/orgs/{org_id}/billing/plan",
        json={"plan": "enterprise-deluxe"},
        headers=_auth(owner_token),
    )

    assert response.status_code == 422


def test_portal_link_requires_an_active_subscription(client: TestClient) -> None:
    org_id, owner_token = _owner_org_token(client, "owner-billing6@example.com", "Billing org 6")

    response = client.get(f"/orgs/{org_id}/billing/portal-link", headers=_auth(owner_token))

    assert response.status_code == 409


@respx.mock
def test_subscribe_creates_a_real_razorpay_customer_and_subscription(
    client: TestClient, razorpay_configured: None
) -> None:
    org_id, owner_token = _owner_org_token(client, "owner-billing7@example.com", "Billing org 7")
    respx.post(f"{_BASE}/customers").mock(
        return_value=httpx.Response(201, json={"id": "cust_fake_router"})
    )
    respx.post(f"{_BASE}/subscriptions").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": "sub_fake_router",
                "status": "created",
                "short_url": "https://rzp.io/i/fake-router",
                "current_end": 1_800_000_000,
            },
        )
    )

    response = client.post(
        f"/orgs/{org_id}/billing/subscribe",
        json={"plan": "starter", "email": "owner-billing7@example.com"},
        headers=_auth(owner_token),
    )

    assert response.status_code == 201, response.text
    assert response.json()["checkout_url"] == "https://rzp.io/i/fake-router"

    billing = client.get(f"/orgs/{org_id}/billing", headers=_auth(owner_token)).json()
    assert billing["plan"] == "starter"


def _sign(body: bytes, *, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _post_razorpay_webhook(
    client: TestClient, payload: dict[str, object], *, secret: str | None = None
) -> httpx.Response:
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if secret is not None:
        headers["X-Razorpay-Signature"] = _sign(body, secret=secret)
    return client.post("/webhooks/razorpay", content=body, headers=headers)


def test_razorpay_webhook_forged_signature_is_rejected(
    client: TestClient, razorpay_webhook_secret_configured: str
) -> None:
    response = _post_razorpay_webhook(
        client,
        {"event": "payment.failed", "payload": {"subscription": {"entity": {"id": "sub_x"}}}},
        secret="not-the-real-secret",
    )
    assert response.status_code == 401


def test_razorpay_webhook_payment_failed_starts_a_grace_period(
    client: TestClient, db_session: Session, razorpay_webhook_secret_configured: str
) -> None:
    org_id, owner_token = _owner_org_token(client, "owner-billing8@example.com", "Billing org 8")
    client.post(
        f"/orgs/{org_id}/billing/plan", json={"plan": "starter"}, headers=_auth(owner_token)
    )

    # Give the org a subscription id directly — the router-level subscribe flow is
    # already covered above; this test is about the webhook's own effect. Uses the
    # same real Postgres connection as `client` (db_session's session_factory), not a
    # second, unrelated connection.
    org = db_session.get(Org, org_id)
    assert org is not None
    org.razorpay_subscription_id = "sub_webhook_test"
    db_session.commit()

    response = _post_razorpay_webhook(
        client,
        {
            "event": "payment.failed",
            "payload": {"subscription": {"entity": {"id": "sub_webhook_test"}}},
        },
        secret=razorpay_webhook_secret_configured,
    )
    assert response.status_code == 200

    billing = client.get(f"/orgs/{org_id}/billing", headers=_auth(owner_token)).json()
    assert billing["billing_status"] == "past_due"
    assert billing["dunning_grace_until"] is not None
