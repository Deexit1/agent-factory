import pytest

from api.db.models import TicketState
from api.domain.state_machine import TransitionRejected, TransitionRequest, validate_transition


def _request(
    from_state: TicketState,
    to_state: TicketState,
    *,
    actor: str = "human:alice",
    bounce_count: int = 0,
    budget_usd: float | None = 100.0,
    acceptance_criteria_count: int = 1,
) -> TransitionRequest:
    return TransitionRequest(
        from_state=from_state,
        to_state=to_state,
        actor=actor,
        bounce_count=bounce_count,
        budget_usd=budget_usd,
        acceptance_criteria_count=acceptance_criteria_count,
    )


def test_ready_to_in_progress_to_in_qa_to_done_is_allowed() -> None:
    validate_transition(_request(TicketState.READY, TicketState.IN_PROGRESS))
    validate_transition(_request(TicketState.IN_PROGRESS, TicketState.IN_QA))
    validate_transition(_request(TicketState.IN_QA, TicketState.DONE))


def test_unwhitelisted_transition_is_rejected() -> None:
    with pytest.raises(TransitionRejected):
        validate_transition(_request(TicketState.READY, TicketState.DONE))


def test_ready_to_in_progress_requires_positive_budget() -> None:
    with pytest.raises(TransitionRejected):
        validate_transition(_request(TicketState.READY, TicketState.IN_PROGRESS, budget_usd=0))

    with pytest.raises(TransitionRejected):
        validate_transition(_request(TicketState.READY, TicketState.IN_PROGRESS, budget_usd=None))


def test_in_qa_to_done_refused_once_bounce_count_maxed() -> None:
    with pytest.raises(TransitionRejected):
        validate_transition(_request(TicketState.IN_QA, TicketState.DONE, bounce_count=3))


def test_in_qa_to_bounced_allowed_below_max_and_refused_at_max() -> None:
    validate_transition(_request(TicketState.IN_QA, TicketState.BOUNCED, bounce_count=2))

    with pytest.raises(TransitionRejected):
        validate_transition(_request(TicketState.IN_QA, TicketState.BOUNCED, bounce_count=3))


def test_in_qa_to_escalated_allowed() -> None:
    validate_transition(_request(TicketState.IN_QA, TicketState.ESCALATED, bounce_count=3))


def test_bounced_to_in_progress_allowed() -> None:
    validate_transition(_request(TicketState.BOUNCED, TicketState.IN_PROGRESS))


def test_planning_to_ready_requires_acceptance_criteria() -> None:
    with pytest.raises(TransitionRejected):
        validate_transition(
            _request(TicketState.PLANNING, TicketState.READY, acceptance_criteria_count=0)
        )

    validate_transition(
        _request(TicketState.PLANNING, TicketState.READY, acceptance_criteria_count=2)
    )


def test_blocked_and_cancelled_require_human_actor_from_any_state() -> None:
    validate_transition(_request(TicketState.IN_PROGRESS, TicketState.BLOCKED))
    validate_transition(_request(TicketState.DONE, TicketState.CANCELLED))

    with pytest.raises(TransitionRejected):
        validate_transition(
            _request(TicketState.IN_PROGRESS, TicketState.BLOCKED, actor="agent:dev-1")
        )


def test_human_actor_detection() -> None:
    from api.domain.state_machine import is_human_actor

    assert is_human_actor("human:alice")
    assert not is_human_actor("agent:dev-1")
    assert not is_human_actor("system")
