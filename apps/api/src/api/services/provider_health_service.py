"""T-202 (SPEC-202): real, callable re-validation of an org's provider keys — not a
background daemon. Matches this repo's consistent "callable entry points, never
auto-triggered" agent architecture (T-104-T-107 precedent): a human, an ops script, or
a future scheduler can call check_org_provider_keys; nothing here assumes one does.
"""

from sqlalchemy.orm import Session

from api.db.models import ProviderKey, ProviderKeyStatus
from api.repositories import provider_key_repository as repo
from api.services.provider_key_service import InvalidProviderKey, validate_key
from api.vault_client import VaultClient


def check_org_provider_keys(
    session: Session, vault: VaultClient, *, org_id: str
) -> list[ProviderKey]:
    checked = []
    for key in repo.list_provider_keys(session, org_id=org_id):
        if key.status == ProviderKeyStatus.REVOKED:
            continue
        secret = vault.get_key(org_id=org_id, provider=key.provider)
        if secret is None:
            repo.update_provider_key_status(
                session, org_id, key.provider, status=ProviderKeyStatus.INVALID
            )
        else:
            try:
                validate_key(provider=key.provider, api_key=secret)
            except InvalidProviderKey:
                repo.update_provider_key_status(
                    session, org_id, key.provider, status=ProviderKeyStatus.INVALID
                )
            else:
                repo.update_provider_key_status(
                    session, org_id, key.provider, status=ProviderKeyStatus.ACTIVE
                )
        checked.append(repo.get_provider_key(session, org_id, key.provider))
    session.commit()
    return [key for key in checked if key is not None]


__all__ = ["check_org_provider_keys"]
