"""T-206 (SPEC-206 AC5): platform-staff-imposed org strikes + appeal handling. Imposing
a strike reuses `billing_service.pause_org_for_nonpayment`'s force-block loop verbatim
— the actor is `human:{staff_email}`, already covered by `state_machine.is_human_actor`,
so no new `_SYSTEM_BLOCK_ACTORS` entry is needed. Appeal *request* is owner-initiated
(self-service); appeal *decision* is platform-staff-only — an org cannot un-strike
itself, unlike billing's automated `payment.captured` unpause (a vendor webhook, no
judgment call involved).
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from api.db.models import Org, OrgStrike, Ticket, TicketState
from api.repositories import abuse_repository
from api.repositories import ticket_repository as repo
from api.services import ticket_service


class AbuseServiceError(Exception):
    pass


class OrgNotFound(AbuseServiceError):
    def __init__(self, org_id: str) -> None:
        self.org_id = org_id
        super().__init__(f"org {org_id} not found")


class StrikeNotFound(AbuseServiceError):
    def __init__(self, strike_id: int) -> None:
        self.strike_id = strike_id
        super().__init__(f"strike {strike_id} not found")


class StrikeNotActive(AbuseServiceError):
    def __init__(self, strike_id: int) -> None:
        self.strike_id = strike_id
        super().__init__(f"strike {strike_id} is not active")


class StrikeNotAppealed(AbuseServiceError):
    def __init__(self, strike_id: int) -> None:
        self.strike_id = strike_id
        super().__init__(f"strike {strike_id} has no pending appeal")


def _get_org(session: Session, org_id: str) -> Org:
    org = session.get(Org, org_id)
    if org is None:
        raise OrgNotFound(org_id)
    return org


def _get_strike(session: Session, strike_id: int) -> OrgStrike:
    strike = abuse_repository.get_strike_any_org(session, strike_id)
    if strike is None:
        raise StrikeNotFound(strike_id)
    return strike


def strike_org(
    session: Session, *, org_id: str, reason: str, actor: str
) -> tuple[OrgStrike, list[Ticket]]:
    """AC5: force-blocks every in-flight ticket — same "in-flight" definition and loop
    shape as billing_service.pause_org_for_nonpayment. "Data retained" is satisfied by
    construction: nothing here deletes anything."""
    _get_org(session, org_id)
    strike = abuse_repository.create_strike(
        session, org_id=org_id, reason=reason, struck_by=actor, struck_at=datetime.now(UTC)
    )
    blocked: list[Ticket] = []
    for ticket in repo.list_in_flight_by_org(session, org_id=org_id):
        updated = ticket_service.request_transition(
            session,
            ticket.id,
            TicketState.BLOCKED,
            actor,
            org_id=org_id,
            reason=f"org struck: {reason}",
        )
        blocked.append(updated)
    session.commit()
    return strike, blocked


def list_strikes(session: Session, *, org_id: str) -> list[OrgStrike]:
    return abuse_repository.list_strikes(session, org_id=org_id)


def request_appeal(
    session: Session, strike_id: int, *, org_id: str, note: str, actor: str
) -> OrgStrike:
    """Owner-initiated, self-service — mirrors org_service.invite_member's owner-only
    gate. A strike belonging to a different org is treated as not-found, matching this
    app's "cross-tenant reads 404, not 403" convention."""
    strike = _get_strike(session, strike_id)
    if strike.org_id != org_id:
        raise StrikeNotFound(strike_id)
    if strike.status != "active":
        raise StrikeNotActive(strike_id)
    abuse_repository.request_appeal(
        session, strike, note=note, appealed_by=actor, appealed_at=datetime.now(UTC)
    )
    session.commit()
    return strike


def resolve_appeal(
    session: Session, strike_id: int, *, decision: str, actor: str
) -> tuple[OrgStrike, list[Ticket]]:
    """Platform-staff-only — never self-service. `reinstate` transitions every
    currently-BLOCKED ticket for the org back to READY via the new BLOCKED -> READY
    state-machine edge; `deny` leaves them blocked. Known, disclosed limitation:
    reactivation is org-wide, not per-strike-cause — no `blocked_reason` column exists
    to distinguish an abuse-block from a simultaneous billing-block."""
    strike = _get_strike(session, strike_id)
    if strike.status != "appealed":
        raise StrikeNotAppealed(strike_id)

    status = "reinstated" if decision == "reinstate" else "denied"
    abuse_repository.resolve_appeal(
        session, strike, status=status, decided_by=actor, decided_at=datetime.now(UTC)
    )

    reactivated: list[Ticket] = []
    if decision == "reinstate":
        for ticket in repo.list_blocked_by_org(session, org_id=strike.org_id):
            updated = ticket_service.request_transition(
                session,
                ticket.id,
                TicketState.READY,
                actor,
                org_id=strike.org_id,
                reason=f"strike {strike_id} appeal reinstated",
            )
            reactivated.append(updated)
    session.commit()
    return strike, reactivated


__all__ = [
    "AbuseServiceError",
    "OrgNotFound",
    "StrikeNotFound",
    "StrikeNotActive",
    "StrikeNotAppealed",
    "strike_org",
    "list_strikes",
    "request_appeal",
    "resolve_appeal",
]
