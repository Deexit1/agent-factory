"""T-202 (SPEC-202): real Vault KV v2 client for BYOK provider keys, stored at
tenants/<org_id>/llm/<provider> per docs/06-tech-stack.md's locked "Tenant secrets
(BYOK)" row. Dev-mode Vault (docker-compose) backs this in local/CI; real production
Vault topology (raft storage, auto-unseal, AppRole auth) is a deploy-time concern, not
this module's.

Callers never persist the return value of get_key() anywhere but a local variable held
for the duration of one agent run (docs/09-saas-model.md's "fetched at run start, held
in memory in the runner, passed to the router").

T-203 (SPEC-203) extends this with put_platform_secret/get_platform_secret at
platform/<name> — for platform-level singletons like the GitHub App's own private key,
distinct from the per-org tenants/<org_id>/... paths above. Minted GitHub installation
tokens themselves are never written to Vault at all (short-lived, mint-on-demand, same
"never persist" doctrine as BYOK keys held in memory).
"""

import os

import hvac
import hvac.exceptions


def _secret_path(*, org_id: str, provider: str) -> str:
    return f"tenants/{org_id}/llm/{provider}"


def _platform_secret_path(name: str) -> str:
    return f"platform/{name}"


class VaultClient:
    def __init__(self, *, addr: str, token: str, mount_point: str = "secret") -> None:
        self._client = hvac.Client(url=addr, token=token)
        self._mount_point = mount_point

    def put_key(self, *, org_id: str, provider: str, api_key: str) -> None:
        self._client.secrets.kv.v2.create_or_update_secret(
            path=_secret_path(org_id=org_id, provider=provider),
            secret={"api_key": api_key},
            mount_point=self._mount_point,
        )

    def get_key(self, *, org_id: str, provider: str) -> str | None:
        try:
            response = self._client.secrets.kv.v2.read_secret_version(
                path=_secret_path(org_id=org_id, provider=provider),
                mount_point=self._mount_point,
                raise_on_deleted_version=True,
            )
        except hvac.exceptions.InvalidPath:
            return None
        api_key = response["data"]["data"]["api_key"]
        return str(api_key)

    def delete_key(self, *, org_id: str, provider: str) -> None:
        try:
            self._client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=_secret_path(org_id=org_id, provider=provider),
                mount_point=self._mount_point,
            )
        except hvac.exceptions.InvalidPath:
            pass

    def put_platform_secret(self, *, name: str, value: str) -> None:
        """T-203: platform-level (non-tenant) secrets, e.g. the GitHub App's own
        private key at platform/github/app-private-key — distinct from the per-org
        tenants/<org_id>/... paths above."""
        self._client.secrets.kv.v2.create_or_update_secret(
            path=_platform_secret_path(name),
            secret={"value": value},
            mount_point=self._mount_point,
        )

    def get_platform_secret(self, *, name: str) -> str | None:
        try:
            response = self._client.secrets.kv.v2.read_secret_version(
                path=_platform_secret_path(name),
                mount_point=self._mount_point,
                raise_on_deleted_version=True,
            )
        except hvac.exceptions.InvalidPath:
            return None
        value = response["data"]["data"]["value"]
        return str(value)


def _default_vault_addr() -> str:
    return os.environ.get("VAULT_ADDR", "http://localhost:8200")


def _default_vault_token() -> str:
    return os.environ.get("VAULT_TOKEN", "")


def get_vault_client() -> VaultClient:
    """FastAPI dependency — reads VAULT_ADDR/VAULT_TOKEN lazily per-request, matching
    api.auth's lazy env-var read pattern (so tests can set env vars after import)."""
    return VaultClient(addr=_default_vault_addr(), token=_default_vault_token())
