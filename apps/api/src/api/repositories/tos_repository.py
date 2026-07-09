from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.models import TosAcceptance


def record_tos_acceptance(
    session: Session, *, org_id: str, accepted_by: str, tos_version: str, accepted_at: datetime
) -> TosAcceptance:
    acceptance = TosAcceptance(
        org_id=org_id, accepted_by=accepted_by, tos_version=tos_version, accepted_at=accepted_at
    )
    session.add(acceptance)
    session.flush()
    return acceptance


def get_latest_tos_acceptance(session: Session, *, org_id: str) -> TosAcceptance | None:
    return session.execute(
        select(TosAcceptance)
        .where(TosAcceptance.org_id == org_id)
        .order_by(TosAcceptance.accepted_at.desc())
        .limit(1)
    ).scalar_one_or_none()


__all__ = ["record_tos_acceptance", "get_latest_tos_acceptance"]
