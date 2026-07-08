from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.models import ProviderEvalOptIn


def create_opt_in(
    session: Session, *, org_id: str, agent_role: str, provider: str, opted_in_by: str
) -> ProviderEvalOptIn:
    opt_in = ProviderEvalOptIn(
        org_id=org_id,
        agent_role=agent_role,
        provider=provider,
        opted_in_by=opted_in_by,
        ts=datetime.now(UTC),
    )
    session.add(opt_in)
    session.flush()
    return opt_in


def get_opt_in(
    session: Session, *, org_id: str, agent_role: str, provider: str
) -> ProviderEvalOptIn | None:
    return session.execute(
        select(ProviderEvalOptIn).where(
            ProviderEvalOptIn.org_id == org_id,
            ProviderEvalOptIn.agent_role == agent_role,
            ProviderEvalOptIn.provider == provider,
        )
    ).scalar_one_or_none()
