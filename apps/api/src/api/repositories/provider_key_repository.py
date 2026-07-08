from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.models import Org, ProviderKey, ProviderKeyStatus


def create_provider_key(
    session: Session, *, org_id: str, provider: str, last4: str, created_by: str
) -> ProviderKey:
    key = ProviderKey(
        org_id=org_id,
        provider=provider,
        last4=last4,
        status=ProviderKeyStatus.ACTIVE,
        created_at=datetime.now(UTC),
        created_by=created_by,
    )
    session.add(key)
    session.flush()
    return key


def get_provider_key(session: Session, org_id: str, provider: str) -> ProviderKey | None:
    return session.execute(
        select(ProviderKey).where(
            ProviderKey.org_id == org_id, ProviderKey.provider == provider
        )
    ).scalar_one_or_none()


def list_provider_keys(session: Session, *, org_id: str) -> list[ProviderKey]:
    return list(
        session.execute(
            select(ProviderKey).where(ProviderKey.org_id == org_id).order_by(ProviderKey.id)
        )
        .scalars()
        .all()
    )


def update_provider_key_status(
    session: Session, org_id: str, provider: str, *, status: ProviderKeyStatus
) -> ProviderKey | None:
    key = get_provider_key(session, org_id, provider)
    if key is None:
        return None
    key.status = status
    session.flush()
    return key


def touch_rotated(
    session: Session, org_id: str, provider: str, *, last4: str
) -> ProviderKey | None:
    key = get_provider_key(session, org_id, provider)
    if key is None:
        return None
    key.last4 = last4
    key.rotated_at = datetime.now(UTC)
    session.flush()
    return key


def delete_provider_key(session: Session, org_id: str, provider: str) -> None:
    key = get_provider_key(session, org_id, provider)
    if key is not None:
        session.delete(key)
        session.flush()


def get_fallback_order(session: Session, org_id: str) -> list[str] | None:
    org = session.get(Org, org_id)
    return org.llm_fallback_order if org is not None else None


def set_fallback_order(session: Session, org_id: str, order: list[str]) -> None:
    org = session.get(Org, org_id)
    if org is not None:
        org.llm_fallback_order = order
        session.flush()
