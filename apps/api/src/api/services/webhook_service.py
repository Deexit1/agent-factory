import hashlib
import hmac
import os

from sqlalchemy.orm import Session

from api.db.models import EventKind, Ticket, TicketState
from api.services import failure_distiller, ticket_service
from api.tenancy import DEFAULT_ORG_ID

CI_ACTOR = "system:ci"


class TicketNotInQA(Exception):
    def __init__(self, ticket_id: str, state: TicketState) -> None:
        self.ticket_id = ticket_id
        self.state = state
        super().__init__(
            f"ticket {ticket_id} is {state.value}, not in_qa; ignoring stale CI result"
        )


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """HMAC-SHA256 over the raw body, GitHub webhook convention (`sha256=<hex>`).

    An unset CI_WEBHOOK_SECRET disables verification — Phase 1 local/dev convenience,
    matching the credential_broker/GitHub client stubs elsewhere in this repo.
    """
    secret = os.environ.get("CI_WEBHOOK_SECRET", "")
    if not secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


def apply_ci_result(
    session: Session,
    ticket_id: str,
    *,
    org_id: str,
    conclusion: str,
    suite: str,
    raw_log: str,
    actor: str = CI_ACTOR,
) -> Ticket:
    """Shared by the custom /webhooks/ci-result route above AND T-203's native GitHub
    check_run.completed handler (github_webhook_service.py) — one transition code path
    for "a CI signal came in", not two independently-drifting copies."""
    ticket = ticket_service.get_ticket(session, ticket_id, org_id=org_id)  # 404s if missing
    if ticket.state is not TicketState.IN_QA:
        raise TicketNotInQA(ticket_id, ticket.state)

    if conclusion == "success":
        # SPEC-106: CI-green no longer completes a ticket directly — it enqueues a
        # real FIFO merge-queue slot; the ticket stays `in_qa` until the queue
        # processor actually rebases, retests, and merges it.
        ticket_service.enqueue_for_merge(session, ticket_id, org_id=org_id)
        return ticket_service.get_ticket(session, ticket_id, org_id=org_id)

    attempt_no = ticket.bounce_count + 1
    report = failure_distiller.distill(
        ticket_id=ticket_id, suite=suite, raw_log=raw_log, attempt_no=attempt_no
    )
    ticket_service.record_event(
        session,
        ticket_id,
        org_id=org_id,
        actor=actor,
        kind=EventKind.TEST_RESULT,
        payload={"conclusion": "failure", "suite": suite, "failure_report": report.model_dump()},
    )

    try:
        return ticket_service.request_transition(
            session, ticket_id, TicketState.BOUNCED, actor=actor, org_id=org_id
        )
    except ticket_service.TransitionRefused as exc:
        if exc.auto_escalated:
            return ticket_service.get_ticket(session, ticket_id, org_id=org_id)
        raise


def handle_ci_result(
    session: Session, ticket_id: str, *, conclusion: str, suite: str, raw_log: str
) -> Ticket:
    # CI webhooks aren't behind an authenticated actor context; scoped to the single
    # seeded org until T-201 gives webhooks a per-org auth token.
    return apply_ci_result(
        session,
        ticket_id,
        org_id=DEFAULT_ORG_ID,
        conclusion=conclusion,
        suite=suite,
        raw_log=raw_log,
    )


__all__ = ["TicketNotInQA", "verify_signature", "handle_ci_result", "apply_ci_result"]
