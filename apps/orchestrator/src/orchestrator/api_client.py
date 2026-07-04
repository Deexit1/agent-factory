from typing import Any

import httpx


class ApiClient:
    """Thin wrapper over the ticket API (apps/api) — the orchestrator never touches
    the database directly, matching the layer-2/layer-5 split in docs/01-architecture.md.
    """

    def __init__(self, base_url: str, actor: str = "system") -> None:
        self._base_url = base_url.rstrip("/")
        self._actor = actor
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"X-Actor": actor, "X-Actor-Role": "admin"},
            timeout=10.0,
        )

    def get_ticket(self, ticket_id: str) -> dict[str, Any]:
        response = self._client.get(f"/tickets/{ticket_id}")
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def append_event(
        self, ticket_id: str, *, actor: str, kind: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        response = self._client.post(
            f"/tickets/{ticket_id}/events",
            json={"actor": actor, "kind": kind, "payload": payload},
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def create_agent_run(
        self, ticket_id: str, *, agent_role: str, model: str, trace_id: str | None = None
    ) -> dict[str, Any]:
        response = self._client.post(
            f"/tickets/{ticket_id}/agent-runs",
            json={"agent_role": agent_role, "model": model, "trace_id": trace_id},
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def complete_agent_run(
        self,
        ticket_id: str,
        run_id: int,
        *,
        status: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
    ) -> dict[str, Any]:
        response = self._client.post(
            f"/tickets/{ticket_id}/agent-runs/{run_id}/complete",
            json={
                "status": status,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost_usd,
            },
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def transition(
        self, ticket_id: str, *, to_state: str, actor: str | None = None
    ) -> dict[str, Any]:
        response = self._client.post(
            f"/tickets/{ticket_id}/transition",
            json={"to_state": to_state, "actor": actor or self._actor},
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def cost_summary(self, ticket_id: str) -> dict[str, Any]:
        response = self._client.get(f"/tickets/{ticket_id}/cost-summary")
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def close(self) -> None:
        self._client.close()
