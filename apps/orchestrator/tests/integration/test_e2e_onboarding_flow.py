"""T-206 (SPEC-206 AC1/AC2/AC3): the genuinely new integration surface T-206 adds — a
freshly created org, self-serve through dev-login (standing in for the real OIDC round
trip, same convention as every other orchestrator/apps/api test in this repo), real
ToS acceptance, and real intake screening — proven against the live HTTP API (not a
bare service-token dogfood ticket in the pre-seeded default org).

**Formerly-disclosed scope limit, resolved by T-211:** this test still does not
continue the new org's idea all the way through planner/dev/review/merge-queue to
`done` — that remains covered nightly, for the one org it's wired for, by
`test_e2e_management_flow.py` (T-109). But the specific blocker that used to make a
non-default-org continuation impossible — `api.auth.get_actor_context` always
resolving the shared service token to `DEFAULT_ORG_ID`, so no single `ApiClient`
could both create/transition tickets in an arbitrary new org AND pass
`get_runtime_keys`'s service-principal check at the same time — is fixed. See
`test_multi_org_dispatch.py::test_planner_agent_runs_for_a_brand_new_non_default_org`
for the actual proof: an `ApiClient(service_token=..., org_id=new_org_id)`, using the
new `X-Org-Id` header (trusted only on the literal service-token auth branch), can
now dispatch a real Planner run for an org it was never a human member of. Extending
*this* test to continue past idea creation into a full agent run is still deferred —
not because it's blocked anymore, just because `test_multi_org_dispatch.py` already
covers the mechanism, and duplicating a full idea-to-done run here isn't necessary.
"""

import json
import urllib.error
import urllib.request
from typing import Any

from .conftest import STAFF_EMAIL


def _request(
    running_api: str,
    path: str,
    *,
    method: str = "GET",
    token: str | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{running_api}{path}", method=method, headers=headers, data=data
    )
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, (json.loads(raw) if raw else None)


def _dev_login(running_api: str, email: str, role: str) -> str:
    status, body = _request(
        running_api, "/auth/dev-login", method="POST", body={"email": email, "role": role}
    )
    assert status == 200, body
    return body["token"]  # type: ignore[no-any-return]


def _create_org(running_api: str, owner_token: str, name: str) -> tuple[str, str]:
    """Signup -> ToS accept -> org create -> switch-org, exactly the sequence the real
    OnboardingWizard UI drives. Returns (org_id, owner_org_token)."""
    tos_status, tos = _request(running_api, "/tos", token=owner_token)
    assert tos_status == 200, tos

    org_status, org = _request(
        running_api,
        "/orgs",
        method="POST",
        token=owner_token,
        body={"name": name, "tos_version": tos["version"]},
    )
    assert org_status == 201, org
    org_id = org["id"]

    # T-206: POST /orgs does NOT re-mint the caller's session token — it still carries
    # the pre-creation org_id/role until switch-org is called explicitly (the same trap
    # OnboardingWizard.tsx/CreateOrgStep.tsx handle in the real UI).
    switch_status, session = _request(
        running_api, "/auth/switch-org", method="POST", token=owner_token, body={"org_id": org_id}
    )
    assert switch_status == 200, session
    assert session["org_id"] == org_id
    assert session["role"] == "owner"
    return org_id, session["token"]


def test_fresh_signup_creates_a_real_org_and_lands_a_screened_idea_in_it(
    running_api: str,
) -> None:
    owner_token = _dev_login(running_api, "onboarding-e2e-owner@example.com", "viewer")
    org_id, owner_org_token = _create_org(running_api, owner_token, "Onboarding E2E Org")

    # Guided first idea (AC1), passes intake screening cleanly (AC2) — a real Ticket
    # row lands in the NEW org, not the seeded default one.
    create_status, idea = _request(
        running_api,
        "/tickets",
        method="POST",
        token=owner_org_token,
        body={
            "type": "idea",
            "title": "Build a customer support dashboard",
            "spec": {"description": "Track and triage support tickets for our SaaS."},
            "budget_usd": 50.0,
            "created_by": "human:onboarding-e2e-owner@example.com",
        },
    )
    assert create_status == 201, idea
    assert idea["org_id"] == org_id
    assert idea["state"] == "approved"

    fetch_status, fetched = _request(
        running_api, f"/tickets/{idea['id']}", token=owner_org_token
    )
    assert fetch_status == 200
    assert fetched["org_id"] == org_id

    # AC3: ToS acceptance really was recorded — a second org-creation attempt with a
    # stale/wrong version is refused, proving the check is real, not a no-op.
    reject_status, reject_body = _request(
        running_api,
        "/orgs",
        method="POST",
        token=owner_token,
        body={"name": "Should be refused", "tos_version": "not-a-real-version"},
    )
    assert reject_status == 422, reject_body


def test_hard_reject_fixture_never_creates_a_ticket_in_the_new_org(running_api: str) -> None:
    """AC2's other half — a prohibited-use fixture is rejected at intake, in a
    brand-new org's own creation flow, not just the pre-seeded default org."""
    owner_token = _dev_login(running_api, "onboarding-e2e-reject@example.com", "viewer")
    org_id, owner_org_token = _create_org(running_api, owner_token, "Onboarding E2E Reject Org")

    status, body = _request(
        running_api,
        "/tickets",
        method="POST",
        token=owner_org_token,
        body={
            "type": "idea",
            "title": "Build a credential stuffing tool",
            "budget_usd": 50.0,
            "created_by": "human:onboarding-e2e-reject@example.com",
        },
    )
    assert status == 422, body
    assert "credential" in body["detail"].lower()

    list_status, tickets = _request(running_api, "/tickets", token=owner_org_token)
    assert list_status == 200
    assert tickets["items"] == []


def test_borderline_idea_is_queued_then_staff_approved_into_the_correct_org(
    running_api: str,
) -> None:
    """AC2's review-queue path, end-to-end through the real staff-only endpoints, for a
    freshly created org — not the default one."""
    owner_token = _dev_login(running_api, "onboarding-e2e-borderline@example.com", "viewer")
    org_id, owner_org_token = _create_org(
        running_api, owner_token, "Onboarding E2E Borderline Org"
    )

    submit_status, submit_body = _request(
        running_api,
        "/tickets",
        method="POST",
        token=owner_org_token,
        body={
            "type": "idea",
            "title": "Build a web scraper for our own product catalog",
            "budget_usd": 50.0,
            "created_by": "human:onboarding-e2e-borderline@example.com",
        },
    )
    assert submit_status == 202, submit_body
    assert submit_body["status"] == "queued_for_review"
    review_id = submit_body["intake_review_id"]

    list_status, tickets = _request(running_api, "/tickets", token=owner_org_token)
    assert list_status == 200
    assert tickets["items"] == []

    # The org owner (not platform staff) is refused — proves the review queue is
    # genuinely staff-gated, not just unenforced.
    forbidden_status, _forbidden_body = _request(
        running_api,
        f"/admin/intake-reviews/{review_id}/approve",
        method="POST",
        token=owner_org_token,
        body={},
    )
    assert forbidden_status == 403

    # A real platform-staff session (STAFF_EMAIL is baked into the running_api
    # subprocess's PLATFORM_STAFF_EMAILS env, conftest.py) approves it for real — the
    # resulting Ticket lands in the SAME org the submission came from.
    staff_token = _dev_login(running_api, STAFF_EMAIL, "viewer")
    approve_status, ticket = _request(
        running_api,
        f"/admin/intake-reviews/{review_id}/approve",
        method="POST",
        token=staff_token,
        body={},
    )
    assert approve_status == 200, ticket
    assert ticket["org_id"] == org_id
    assert ticket["type"] == "idea"

    list_status, tickets = _request(running_api, "/tickets", token=owner_org_token)
    assert list_status == 200
    assert len(tickets["items"]) == 1
    assert tickets["items"][0]["id"] == ticket["id"]
