from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.auth import SERVICE_ACTOR, ActorContext, get_actor_context
from api.contracts import (
    AddProviderKeyRequest,
    ProviderCredentialOut,
    ProviderKeyListOut,
    ProviderKeyOut,
    RuntimeKeysOut,
    SetFallbackOrderRequest,
)
from api.db.session import get_db
from api.services import provider_health_service, provider_key_service
from api.vault_client import VaultClient, get_vault_client

router = APIRouter(
    prefix="/orgs/{org_id}/provider-keys",
    tags=["provider-keys"],
    dependencies=[Depends(get_actor_context)],
)

# Separate prefix (not nested under provider-keys) for the internal, service-token-only
# route that returns actual key material — kept visually and structurally distinct
# from the owner-facing CRUD routes above it.
runtime_router = APIRouter(
    prefix="/orgs/{org_id}/llm", tags=["provider-keys"], dependencies=[Depends(get_actor_context)]
)


def _actor_email(actor_context: ActorContext) -> str:
    return actor_context.actor.removeprefix("human:").removeprefix("staff:")


def _require_member(org_id: str, actor_context: ActorContext) -> None:
    # Cross-tenant reads 404, not 403 (T-201 AC1 convention).
    if actor_context.org_id != org_id:
        raise HTTPException(status_code=404, detail="org not found")


def _require_owner(org_id: str, actor_context: ActorContext) -> None:
    _require_member(org_id, actor_context)
    if actor_context.role != "owner":
        raise HTTPException(status_code=403, detail="only the org owner may manage provider keys")


@router.get("", response_model=ProviderKeyListOut)
def list_keys(
    org_id: str,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> ProviderKeyListOut:
    _require_member(org_id, actor_context)
    keys = provider_key_service.list_keys(db, org_id=org_id)
    return ProviderKeyListOut(items=[ProviderKeyOut.model_validate(k) for k in keys])


@router.post("", response_model=ProviderKeyOut, status_code=201)
def add_key(
    org_id: str,
    request: AddProviderKeyRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
    vault: VaultClient = Depends(get_vault_client),
) -> ProviderKeyOut:
    _require_owner(org_id, actor_context)
    try:
        key = provider_key_service.add_or_rotate_key(
            db,
            vault,
            org_id=org_id,
            provider=request.provider,
            api_key=request.api_key,
            actor_email=_actor_email(actor_context),
        )
    except provider_key_service.InvalidProviderKey as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ProviderKeyOut.model_validate(key)


@router.post("/{provider}/rotate", response_model=ProviderKeyOut)
def rotate_key(
    org_id: str,
    provider: str,
    request: AddProviderKeyRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
    vault: VaultClient = Depends(get_vault_client),
) -> ProviderKeyOut:
    _require_owner(org_id, actor_context)
    if provider != request.provider:
        raise HTTPException(status_code=422, detail="provider in path and body must match")
    try:
        key = provider_key_service.add_or_rotate_key(
            db,
            vault,
            org_id=org_id,
            provider=request.provider,
            api_key=request.api_key,
            actor_email=_actor_email(actor_context),
        )
    except provider_key_service.InvalidProviderKey as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ProviderKeyOut.model_validate(key)


@router.delete("/{provider}", status_code=204)
def delete_key(
    org_id: str,
    provider: str,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
    vault: VaultClient = Depends(get_vault_client),
) -> None:
    _require_owner(org_id, actor_context)
    provider_key_service.delete_key(db, vault, org_id=org_id, provider=provider)


@router.put("/fallback-order", response_model=ProviderKeyListOut)
def set_fallback_order(
    org_id: str,
    request: SetFallbackOrderRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> ProviderKeyListOut:
    _require_owner(org_id, actor_context)
    provider_key_service.set_fallback_order(db, org_id=org_id, order=request.order)
    keys = provider_key_service.list_keys(db, org_id=org_id)
    return ProviderKeyListOut(items=[ProviderKeyOut.model_validate(k) for k in keys])


@router.post("/health-check", response_model=ProviderKeyListOut)
def health_check(
    org_id: str,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
    vault: VaultClient = Depends(get_vault_client),
) -> ProviderKeyListOut:
    _require_member(org_id, actor_context)
    if actor_context.role != "owner" and not actor_context.is_platform_staff:
        raise HTTPException(
            status_code=403,
            detail="only the org owner or platform staff may trigger a health check",
        )
    keys = provider_health_service.check_org_provider_keys(db, vault, org_id=org_id)
    return ProviderKeyListOut(items=[ProviderKeyOut.model_validate(k) for k in keys])


@runtime_router.get("/runtime-keys", response_model=RuntimeKeysOut)
def get_runtime_keys(
    org_id: str,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
    vault: VaultClient = Depends(get_vault_client),
) -> RuntimeKeysOut:
    if actor_context.actor != SERVICE_ACTOR:
        raise HTTPException(
            status_code=403, detail="runtime key resolution is service-principal only"
        )
    credentials = provider_key_service.resolve_runtime_credentials(db, vault, org_id=org_id)
    return RuntimeKeysOut(
        items=[ProviderCredentialOut(**credential) for credential in credentials]
    )
