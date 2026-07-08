from fastapi import APIRouter, Depends, HTTPException

from api.artifact_storage import (
    ArtifactStorageConfig,
    get_artifact_storage_config,
    mint_scoped_credential,
)
from api.auth import ActorContext, get_actor_context
from api.contracts import ArtifactCredentialOut

router = APIRouter(
    prefix="/orgs/{org_id}",
    tags=["artifacts"],
    dependencies=[Depends(get_actor_context)],
)


def _require_member(org_id: str, actor_context: ActorContext) -> None:
    # Cross-tenant reads 404, not 403 (T-201 AC1 convention).
    if actor_context.org_id != org_id:
        raise HTTPException(status_code=404, detail="org not found")


@router.post("/artifact-credentials", response_model=ArtifactCredentialOut, status_code=201)
def mint_artifact_credential(
    org_id: str,
    actor_context: ActorContext = Depends(get_actor_context),
    storage_config: ArtifactStorageConfig = Depends(get_artifact_storage_config),
) -> ArtifactCredentialOut:
    _require_member(org_id, actor_context)
    credential = mint_scoped_credential(storage_config, org_id=org_id)
    return ArtifactCredentialOut(
        access_key=credential.access_key,
        secret_key=credential.secret_key,
        session_token=credential.session_token,
        bucket=credential.bucket,
        prefix=credential.prefix,
        expires_at=credential.expires_at,
    )
