from sqlalchemy.orm import Session

from api.contracts import EvalFloorOut
from api.eval_floors import load_provider_floor
from api.repositories import provider_eval_opt_in_repository as opt_in_repo


def get_eval_floor(
    session: Session, *, org_id: str, agent_role: str, provider: str
) -> EvalFloorOut:
    floor = load_provider_floor(agent_role, provider)
    opted_in = (
        opt_in_repo.get_opt_in(session, org_id=org_id, agent_role=agent_role, provider=provider)
        is not None
    )
    return EvalFloorOut(
        agent_role=agent_role,
        provider=provider,
        verified=floor.verified,
        floor=floor.floor,
        opted_in=opted_in,
    )


def is_dispatchable(session: Session, *, org_id: str, agent_role: str, provider: str) -> bool:
    """A (role, provider) combo is dispatchable if it has a green eval floor, or the
    org has explicitly opted into "unverified quality" for it (SPEC-202 AC5) — a hard
    gate enforced at agent dispatch, not a UI-only suggestion."""
    floor = load_provider_floor(agent_role, provider)
    if floor.verified:
        return True
    return (
        opt_in_repo.get_opt_in(session, org_id=org_id, agent_role=agent_role, provider=provider)
        is not None
    )


def opt_in(
    session: Session, *, org_id: str, agent_role: str, provider: str, actor_email: str
) -> None:
    existing = opt_in_repo.get_opt_in(
        session, org_id=org_id, agent_role=agent_role, provider=provider
    )
    if existing is None:
        opt_in_repo.create_opt_in(
            session,
            org_id=org_id,
            agent_role=agent_role,
            provider=provider,
            opted_in_by=actor_email,
        )
        session.commit()


__all__ = ["get_eval_floor", "is_dispatchable", "opt_in"]
