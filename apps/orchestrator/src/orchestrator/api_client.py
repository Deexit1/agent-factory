import os
from typing import Any

import httpx


class ApiClient:
    """Thin wrapper over the ticket API (apps/api) — the orchestrator never touches
    the database directly, matching the layer-2/layer-5 split in docs/01-architecture.md.

    Authenticates as the trusted service principal (SPEC-006 AC1: every apps/api route
    except /health, /webhooks/*, /auth/* requires a bearer token) via the shared secret
    both sides read from AGENT_FACTORY_SERVICE_TOKEN.
    """

    def __init__(
        self, base_url: str, actor: str = "system", service_token: str | None = None
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._actor = actor
        token = service_token or os.environ.get("AGENT_FACTORY_SERVICE_TOKEN", "")
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )

    def get_ticket(self, ticket_id: str) -> dict[str, Any]:
        response = self._client.get(f"/tickets/{ticket_id}")
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def create_ticket(
        self,
        *,
        ticket_type: str,
        title: str,
        created_by: str,
        parent_id: str | None = None,
        budget_usd: float | None = None,
        acceptance_criteria: list[dict[str, Any]] | None = None,
        spec: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self._client.post(
            "/tickets",
            json={
                "type": ticket_type,
                "title": title,
                "created_by": created_by,
                "parent_id": parent_id,
                "budget_usd": budget_usd,
                "acceptance_criteria": acceptance_criteria or [],
                "spec": spec,
            },
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def descendants(self, ticket_id: str) -> list[dict[str, Any]]:
        response = self._client.get(f"/tickets/{ticket_id}/descendants")
        response.raise_for_status()
        return response.json()["items"]  # type: ignore[no-any-return]

    def list_tickets(
        self,
        *,
        state: str | None = None,
        ticket_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if state is not None:
            params["state"] = state
        if ticket_type is not None:
            params["type"] = ticket_type
        response = self._client.get("/tickets", params=params)
        response.raise_for_status()
        return response.json()["items"]  # type: ignore[no-any-return]

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
        self,
        ticket_id: str,
        *,
        agent_role: str,
        model: str,
        trace_id: str | None = None,
        prompt_version: str | None = None,
    ) -> dict[str, Any]:
        response = self._client.post(
            f"/tickets/{ticket_id}/agent-runs",
            json={
                "agent_role": agent_role,
                "model": model,
                "trace_id": trace_id,
                "prompt_version": prompt_version,
            },
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
        self,
        ticket_id: str,
        *,
        to_state: str,
        actor: str | None = None,
        assignee_agent: str | None = None,
    ) -> dict[str, Any]:
        response = self._client.post(
            f"/tickets/{ticket_id}/transition",
            json={
                "to_state": to_state,
                "actor": actor or self._actor,
                "assignee_agent": assignee_agent,
            },
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def cost_summary(self, ticket_id: str) -> dict[str, Any]:
        response = self._client.get(f"/tickets/{ticket_id}/cost-summary")
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def utilisation(self) -> list[dict[str, Any]]:
        response = self._client.get("/capability-registry/utilisation")
        response.raise_for_status()
        return response.json()["items"]  # type: ignore[no-any-return]

    def report_ci_result(
        self, ticket_id: str, *, conclusion: str, suite: str = "", raw_log: str = ""
    ) -> dict[str, Any]:
        response = self._client.post(
            "/webhooks/ci-result",
            json={
                "ticket_id": ticket_id,
                "conclusion": conclusion,
                "suite": suite,
                "raw_log": raw_log,
            },
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def list_merge_queue_entries(self, *, repo: str) -> list[dict[str, Any]]:
        response = self._client.get("/merge-queue", params={"repo": repo})
        response.raise_for_status()
        return response.json()["items"]  # type: ignore[no-any-return]

    def resolve_merge_success(self, entry_id: int, *, actor: str) -> dict[str, Any]:
        response = self._client.post(
            f"/merge-queue/{entry_id}/merge", json={"actor": actor}
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def resolve_merge_conflict(
        self, entry_id: int, *, actor: str, conflicting_paths: list[str]
    ) -> dict[str, Any]:
        response = self._client.post(
            f"/merge-queue/{entry_id}/conflict",
            json={"actor": actor, "conflicting_paths": conflicting_paths},
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def close(self) -> None:
        self._client.close()
