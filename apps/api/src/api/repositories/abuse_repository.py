from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.models import OrgStrike


def create_strike(
    session: Session, *, org_id: str, reason: str, struck_by: str, struck_at: datetime
) -> OrgStrike:
    strike = OrgStrike(
        org_id=org_id, reason=reason, struck_by=struck_by, struck_at=struck_at, status="active"
    )
    session.add(strike)
    session.flush()
    return strike


def get_strike(session: Session, strike_id: int, *, org_id: str) -> OrgStrike | None:
    strike = session.get(OrgStrike, strike_id)
    if strike is None or strike.org_id != org_id:
        return None
    return strike


def get_strike_any_org(session: Session, strike_id: int) -> OrgStrike | None:
    """Staff-only lookup — same "no single org_id to scope by" shape as
    intake_repository.get_intake_review_any_org; the caller (a platform-staff-gated
    route) is the enforcement point."""
    return session.get(OrgStrike, strike_id)


def list_strikes(session: Session, *, org_id: str) -> list[OrgStrike]:
    return list(
        session.execute(
            select(OrgStrike).where(OrgStrike.org_id == org_id).order_by(OrgStrike.struck_at.desc())
        )
        .scalars()
        .all()
    )


def request_appeal(
    session: Session, strike: OrgStrike, *, note: str, appealed_by: str, appealed_at: datetime
) -> OrgStrike:
    strike.status = "appealed"
    strike.appeal_note = note
    strike.appealed_by = appealed_by
    strike.appealed_at = appealed_at
    session.flush()
    return strike


def resolve_appeal(
    session: Session,
    strike: OrgStrike,
    *,
    status: str,
    decided_by: str,
    decided_at: datetime,
) -> OrgStrike:
    strike.status = status
    strike.appeal_decided_by = decided_by
    strike.appeal_decided_at = decided_at
    session.flush()
    return strike


__all__ = [
    "create_strike",
    "get_strike",
    "get_strike_any_org",
    "list_strikes",
    "request_appeal",
    "resolve_appeal",
]
