"""T-202 (SPEC-202): key management service — Vault write/delete + DB metadata.

The `_validate_key` ping below is the one, disclosed, narrow exception to "provider
SDKs live only in packages/llm_router" (scripts/check_llm_router_gate.py's
_ALLOWLISTED_FILES): it's a cheap `models.list()`-shaped call proving a newly-added key
is live, never a completion call, never touches agent_runs/cost_ledger, and stays out
of packages/llm_router entirely because llm_router's job is routing real agent calls,
not validating a key a human just pasted into a form.
"""

import os

import anthropic
import openai
from sqlalchemy.orm import Session

from api.db.models import ProviderKey, ProviderKeyStatus
from api.repositories import provider_key_repository as repo
from api.vault_client import VaultClient


class InvalidProviderKey(Exception):
    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"could not validate a live {provider} key")


def validate_key(*, provider: str, api_key: str) -> None:
    try:
        if provider == "anthropic":
            anthropic.Anthropic(api_key=api_key).models.list(limit=1)
        elif provider == "openai":
            openai.OpenAI(api_key=api_key).models.list()
    except Exception as exc:  # noqa: BLE001 — any SDK error means "not a live key"
        raise InvalidProviderKey(provider) from exc


def add_or_rotate_key(
    session: Session,
    vault: VaultClient,
    *,
    org_id: str,
    provider: str,
    api_key: str,
    actor_email: str,
) -> ProviderKey:
    validate_key(provider=provider, api_key=api_key)
    vault.put_key(org_id=org_id, provider=provider, api_key=api_key)

    existing = repo.get_provider_key(session, org_id, provider)
    key: ProviderKey | None
    if existing is None:
        key = repo.create_provider_key(
            session, org_id=org_id, provider=provider, last4=api_key[-4:], created_by=actor_email
        )
    else:
        repo.touch_rotated(session, org_id, provider, last4=api_key[-4:])
        key = repo.update_provider_key_status(
            session, org_id, provider, status=ProviderKeyStatus.ACTIVE
        )
    assert key is not None
    session.commit()
    return key


def delete_key(session: Session, vault: VaultClient, *, org_id: str, provider: str) -> None:
    vault.delete_key(org_id=org_id, provider=provider)
    repo.update_provider_key_status(session, org_id, provider, status=ProviderKeyStatus.REVOKED)
    session.commit()


def list_keys(session: Session, *, org_id: str) -> list[ProviderKey]:
    return repo.list_provider_keys(session, org_id=org_id)


def get_fallback_order(session: Session, *, org_id: str) -> list[str] | None:
    return repo.get_fallback_order(session, org_id)


def set_fallback_order(session: Session, *, org_id: str, order: list[str]) -> None:
    repo.set_fallback_order(session, org_id, order)
    session.commit()


def resolve_runtime_credentials(
    session: Session, vault: VaultClient, *, org_id: str
) -> list[dict[str, str]]:
    """Only ACTIVE keys, in the org's fallback order (default: anthropic first) —
    this is the single enforcement point behind AC6's "paused within 60s": a revoked
    key simply never appears here again, and every dispatch calls this fresh.

    An org that has NEVER configured any BYOK key at all (no ProviderKey row of any
    status) falls back to the platform's own ANTHROPIC_API_KEY — the pre-T-202
    behavior, unchanged, so every pre-BYOK org/test/pilot script keeps working with
    zero setup. This fallback stops applying the moment an org configures its own key
    (ACTIVE or REVOKED) — from then on AC6 governs: delete pauses, it doesn't silently
    fall back to the platform's key.
    """
    all_keys = repo.list_provider_keys(session, org_id=org_id)
    if not all_keys:
        platform_key = os.environ.get("ANTHROPIC_API_KEY", "")
        return [{"provider": "anthropic", "api_key": platform_key}] if platform_key else []

    order = repo.get_fallback_order(session, org_id) or ["anthropic", "openai"]
    active = {key.provider: key for key in all_keys if key.status == ProviderKeyStatus.ACTIVE}
    credentials = []
    for provider in order:
        key_row = active.get(provider)
        if key_row is None:
            continue
        secret = vault.get_key(org_id=org_id, provider=provider)
        if secret:
            credentials.append({"provider": provider, "api_key": secret})
    return credentials


__all__ = [
    "InvalidProviderKey",
    "validate_key",
    "add_or_rotate_key",
    "delete_key",
    "list_keys",
    "get_fallback_order",
    "set_fallback_order",
    "resolve_runtime_credentials",
]
