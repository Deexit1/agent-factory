from dataclasses import dataclass

from api.db.models import TicketState

MAX_BOUNCES = 3

_BASE_TRANSITIONS: dict[TicketState, set[TicketState]] = {
    TicketState.PROPOSED: {TicketState.EXEC_REVIEW},
    TicketState.EXEC_REVIEW: {TicketState.AWAITING_HUMAN_GO},
    TicketState.AWAITING_HUMAN_GO: {TicketState.APPROVED, TicketState.CANCELLED},
    TicketState.APPROVED: {TicketState.PLANNING},
    TicketState.PLANNING: {TicketState.READY},
    TicketState.READY: {TicketState.IN_PROGRESS},
    TicketState.IN_PROGRESS: {TicketState.IN_QA, TicketState.ESCALATED},
    TicketState.IN_QA: {TicketState.DONE, TicketState.BOUNCED, TicketState.ESCALATED},
    TicketState.BOUNCED: {TicketState.IN_PROGRESS},
}

# Every state may transition here, but only a human actor may request it.
_HUMAN_ONLY_TARGETS = {TicketState.BLOCKED, TicketState.CANCELLED}


@dataclass(frozen=True)
class TransitionRequest:
    from_state: TicketState
    to_state: TicketState
    actor: str
    bounce_count: int
    budget_usd: float | None
    acceptance_criteria_count: int


class TransitionRejected(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def is_human_actor(actor: str) -> bool:
    return actor.startswith("human:")


def validate_transition(request: TransitionRequest) -> None:
    """Raise TransitionRejected if the requested transition is illegal.

    Pure function: no I/O, no mutation.
    """
    if request.to_state in _HUMAN_ONLY_TARGETS:
        if not is_human_actor(request.actor):
            raise TransitionRejected(f"{request.to_state} may only be requested by a human actor")
        return

    allowed = _BASE_TRANSITIONS.get(request.from_state, set())
    if request.to_state not in allowed:
        raise TransitionRejected(
            f"{request.from_state} -> {request.to_state} is not a whitelisted transition"
        )

    _check_guard(request)


def _check_guard(request: TransitionRequest) -> None:
    if request.from_state is TicketState.PLANNING and request.to_state is TicketState.READY:
        if request.acceptance_criteria_count == 0:
            raise TransitionRejected("every task must have acceptance_criteria before ready")

    if request.from_state is TicketState.READY and request.to_state is TicketState.IN_PROGRESS:
        if not request.budget_usd or request.budget_usd <= 0:
            raise TransitionRejected("budget_usd must be > 0 before starting work")

    if request.from_state is TicketState.IN_QA and request.to_state is TicketState.DONE:
        if request.bounce_count >= MAX_BOUNCES:
            raise TransitionRejected(
                f"bounce_count reached the max ({MAX_BOUNCES}); ticket must be escalated, not done"
            )

    if request.from_state is TicketState.IN_QA and request.to_state is TicketState.BOUNCED:
        if request.bounce_count >= MAX_BOUNCES:
            raise TransitionRejected(
                f"bounce_count reached the max ({MAX_BOUNCES}); "
                "ticket must be escalated, not bounced again"
            )
