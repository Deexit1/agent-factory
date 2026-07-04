import os

import httpx


def post_event(
    api_url: str, ticket_id: str, *, actor: str, kind: str, payload: dict[str, object]
) -> None:
    token = os.environ.get("AGENT_FACTORY_SERVICE_TOKEN", "")
    response = httpx.post(
        f"{api_url}/tickets/{ticket_id}/events",
        json={"actor": actor, "kind": kind, "payload": payload},
        headers={"Authorization": f"Bearer {token}"},
        timeout=5.0,
    )
    response.raise_for_status()
