"""T-202 (SPEC-202 AC5): selecting an uneval'd (agent_role, provider) combo shows the
badge (verified=False) and requires an explicit, recorded opt-in before it's treated
as dispatchable."""

from fastapi.testclient import TestClient

from .test_tickets_api import _dev_login


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_anthropic_is_verified_for_dev_no_opt_in_needed(client: TestClient) -> None:
    owner_token = _dev_login(client, "floors-owner1@example.com", "owner")
    org = client.post("/orgs", json={"name": "Floors org 1"}, headers=_auth(owner_token)).json()
    owner_org_token = client.post(
        "/auth/switch-org", json={"org_id": org["id"]}, headers=_auth(owner_token)
    ).json()["token"]

    response = client.get(
        f"/orgs/{org['id']}/eval-floors",
        params={"agent_role": "dev", "provider": "anthropic"},
        headers=_auth(owner_org_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["verified"] is True
    assert body["opted_in"] is False


def test_openai_is_unverified_for_dev_and_requires_opt_in(client: TestClient) -> None:
    owner_token = _dev_login(client, "floors-owner2@example.com", "owner")
    org = client.post("/orgs", json={"name": "Floors org 2"}, headers=_auth(owner_token)).json()
    owner_org_token = client.post(
        "/auth/switch-org", json={"org_id": org["id"]}, headers=_auth(owner_token)
    ).json()["token"]

    before = client.get(
        f"/orgs/{org['id']}/eval-floors",
        params={"agent_role": "dev", "provider": "openai"},
        headers=_auth(owner_org_token),
    ).json()
    assert before["verified"] is False
    assert before["opted_in"] is False

    opt_in = client.post(
        f"/orgs/{org['id']}/eval-floors/opt-in",
        json={"agent_role": "dev", "provider": "openai"},
        headers=_auth(owner_org_token),
    )
    assert opt_in.status_code == 201, opt_in.text
    assert opt_in.json()["opted_in"] is True

    after = client.get(
        f"/orgs/{org['id']}/eval-floors",
        params={"agent_role": "dev", "provider": "openai"},
        headers=_auth(owner_org_token),
    ).json()
    assert after["opted_in"] is True
    assert after["verified"] is False  # opting in doesn't fabricate a real floor


def test_delivery_manager_has_no_eval_floor_concept_so_it_is_never_gated(
    client: TestClient,
) -> None:
    owner_token = _dev_login(client, "floors-owner3@example.com", "owner")
    org = client.post("/orgs", json={"name": "Floors org 3"}, headers=_auth(owner_token)).json()
    owner_org_token = client.post(
        "/auth/switch-org", json={"org_id": org["id"]}, headers=_auth(owner_token)
    ).json()["token"]

    response = client.get(
        f"/orgs/{org['id']}/eval-floors",
        params={"agent_role": "delivery-manager", "provider": "anthropic"},
        headers=_auth(owner_org_token),
    ).json()
    assert response["verified"] is True
    assert response["floor"] is None


def test_non_owner_cannot_opt_in(client: TestClient) -> None:
    owner_token = _dev_login(client, "floors-owner4@example.com", "owner")
    org = client.post("/orgs", json={"name": "Floors org 4"}, headers=_auth(owner_token)).json()
    owner_org_token = client.post(
        "/auth/switch-org", json={"org_id": org["id"]}, headers=_auth(owner_token)
    ).json()["token"]
    invite = client.post(
        f"/orgs/{org['id']}/invites",
        json={"email": "floors-viewer@example.com", "role": "viewer"},
        headers=_auth(owner_org_token),
    ).json()
    viewer_session = _dev_login(client, "floors-viewer@example.com", "viewer")
    client.post(f"/orgs/invites/{invite['token']}/accept", headers=_auth(viewer_session))
    viewer_org_token = client.post(
        "/auth/switch-org", json={"org_id": org["id"]}, headers=_auth(viewer_session)
    ).json()["token"]

    response = client.post(
        f"/orgs/{org['id']}/eval-floors/opt-in",
        json={"agent_role": "dev", "provider": "openai"},
        headers=_auth(viewer_org_token),
    )
    assert response.status_code == 403
