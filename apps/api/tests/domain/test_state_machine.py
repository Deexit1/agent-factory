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
    plan_task_count: int = 0,
    plan_has_cycle: bool = False,
    plan_child_budget_total: float = 0.0,
    plan_has_budget_approval: bool = False,
    deps_done: bool = True,
    spent_usd: float = 0.0,
    assignee_agent: str | None = None,
    profile_at_capacity: bool = False,
    repo_at_capacity: bool = False,
) -> TransitionRequest:
    return TransitionRequest(
        from_state=from_state,
        to_state=to_state,
        actor=actor,
        bounce_count=bounce_count,
        budget_usd=budget_usd,
        acceptance_criteria_count=acceptance_criteria_count,
        plan_task_count=plan_task_count,
        plan_has_cycle=plan_has_cycle,
        plan_child_budget_total=plan_child_budget_total,
        plan_has_budget_approval=plan_has_budget_approval,
        deps_done=deps_done,
        spent_usd=spent_usd,
        assignee_agent=assignee_agent,
        profile_at_capacity=profile_at_capacity,
        repo_at_capacity=repo_at_capacity,
    )


def test_ready_to_in_progress_to_in_review_to_in_qa_to_done_is_allowed() -> None:
    validate_transition(_request(TicketState.READY, TicketState.IN_PROGRESS))
    validate_transition(_request(TicketState.IN_PROGRESS, TicketState.IN_REVIEW))
    validate_transition(_request(TicketState.IN_REVIEW, TicketState.IN_QA))
    validate_transition(_request(TicketState.IN_QA, TicketState.DONE))


def test_unwhitelisted_transition_is_rejected() -> None:
    with pytest.raises(TransitionRejected):
        validate_transition(_request(TicketState.READY, TicketState.DONE))

    # in_progress can no longer skip the review gate directly to in_qa
    with pytest.raises(TransitionRejected):
        validate_transition(_request(TicketState.IN_PROGRESS, TicketState.IN_QA))


def test_in_review_to_bounced_allowed_below_max_and_refused_at_max() -> None:
    validate_transition(_request(TicketState.IN_REVIEW, TicketState.BOUNCED, bounce_count=2))

    with pytest.raises(TransitionRejected):
        validate_transition(_request(TicketState.IN_REVIEW, TicketState.BOUNCED, bounce_count=3))


def test_in_review_to_escalated_allowed() -> None:
    validate_transition(_request(TicketState.IN_REVIEW, TicketState.ESCALATED, bounce_count=3))


def test_in_progress_to_escalated_allowed_for_budget_or_timeout() -> None:
    validate_transition(_request(TicketState.IN_PROGRESS, TicketState.ESCALATED))


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


def test_escalated_to_in_progress_requires_human_actor() -> None:
    validate_transition(
        _request(TicketState.ESCALATED, TicketState.IN_PROGRESS, actor="human:alice")
    )

    with pytest.raises(TransitionRejected):
        validate_transition(
            _request(TicketState.ESCALATED, TicketState.IN_PROGRESS, actor="agent:dev-1")
        )


def test_planning_to_ready_requires_acceptance_criteria() -> None:
    with pytest.raises(TransitionRejected):
        validate_transition(
            _request(TicketState.PLANNING, TicketState.READY, acceptance_criteria_count=0)
        )

    validate_transition(
        _request(TicketState.PLANNING, TicketState.READY, acceptance_criteria_count=2)
    )


def test_approved_to_planning_requires_positive_budget() -> None:
    validate_transition(_request(TicketState.APPROVED, TicketState.PLANNING, budget_usd=50.0))

    with pytest.raises(TransitionRejected):
        validate_transition(_request(TicketState.APPROVED, TicketState.PLANNING, budget_usd=0))


def test_planning_to_ready_with_a_real_plan_requires_dag_budget_and_approval() -> None:
    # A cyclic dependency graph blocks ready even if everything else is fine (AC3).
    with pytest.raises(TransitionRejected, match="cycle"):
        validate_transition(
            _request(
                TicketState.PLANNING,
                TicketState.READY,
                plan_task_count=2,
                plan_has_cycle=True,
                plan_child_budget_total=50.0,
                plan_has_budget_approval=True,
            )
        )

    # Task budgets exceeding the idea's budget block ready (AC4).
    with pytest.raises(TransitionRejected, match="exceeds"):
        validate_transition(
            _request(
                TicketState.PLANNING,
                TicketState.READY,
                budget_usd=100.0,
                plan_task_count=2,
                plan_child_budget_total=150.0,
                plan_has_budget_approval=True,
            )
        )

    # No recorded budget-gate approval blocks ready even with a valid, in-budget plan.
    with pytest.raises(TransitionRejected, match="approved budget gate"):
        validate_transition(
            _request(
                TicketState.PLANNING,
                TicketState.READY,
                budget_usd=100.0,
                plan_task_count=2,
                plan_child_budget_total=50.0,
                plan_has_budget_approval=False,
            )
        )

    # All gates satisfied -> allowed.
    validate_transition(
        _request(
            TicketState.PLANNING,
            TicketState.READY,
            budget_usd=100.0,
            plan_task_count=2,
            plan_child_budget_total=50.0,
            plan_has_budget_approval=True,
        )
    )


def test_planning_to_escalated_allowed_for_planner_or_human() -> None:
    validate_transition(
        _request(TicketState.PLANNING, TicketState.ESCALATED, actor="agent:planner-1")
    )
    validate_transition(_request(TicketState.PLANNING, TicketState.ESCALATED, actor="human:alice"))

    with pytest.raises(TransitionRejected):
        validate_transition(
            _request(TicketState.PLANNING, TicketState.ESCALATED, actor="agent:dev-1")
        )


def test_escalated_to_planning_requires_human_actor() -> None:
    validate_transition(_request(TicketState.ESCALATED, TicketState.PLANNING, actor="human:alice"))

    with pytest.raises(TransitionRejected):
        validate_transition(
            _request(TicketState.ESCALATED, TicketState.PLANNING, actor="agent:planner-1")
        )


def test_ready_to_in_progress_refused_when_task_already_spent_its_budget() -> None:
    validate_transition(
        _request(TicketState.READY, TicketState.IN_PROGRESS, budget_usd=100.0, spent_usd=99.99)
    )

    with pytest.raises(TransitionRejected, match="already spent its budget"):
        validate_transition(
            _request(TicketState.READY, TicketState.IN_PROGRESS, budget_usd=100.0, spent_usd=100.0)
        )


def test_ready_to_in_progress_refused_when_dependencies_not_done() -> None:
    with pytest.raises(TransitionRejected, match="dependencies are not done"):
        validate_transition(
            _request(TicketState.READY, TicketState.IN_PROGRESS, deps_done=False)
        )


def test_ready_to_in_progress_refused_when_profile_or_repo_at_capacity() -> None:
    # No assignee_agent proposed -> capacity checks don't apply (e.g. a direct,
    # non-DM-mediated transition).
    validate_transition(
        _request(
            TicketState.READY,
            TicketState.IN_PROGRESS,
            assignee_agent=None,
            profile_at_capacity=True,
            repo_at_capacity=True,
        )
    )

    with pytest.raises(TransitionRejected, match="max_parallel capacity"):
        validate_transition(
            _request(
                TicketState.READY,
                TicketState.IN_PROGRESS,
                assignee_agent="dev-generalist",
                profile_at_capacity=True,
            )
        )

    with pytest.raises(TransitionRejected, match="concurrency limit"):
        validate_transition(
            _request(
                TicketState.READY,
                TicketState.IN_PROGRESS,
                assignee_agent="dev-generalist",
                repo_at_capacity=True,
            )
        )

    validate_transition(
        _request(TicketState.READY, TicketState.IN_PROGRESS, assignee_agent="dev-generalist")
    )


def test_escalated_to_ready_requires_human_actor() -> None:
    validate_transition(_request(TicketState.ESCALATED, TicketState.READY, actor="human:alice"))

    with pytest.raises(TransitionRejected):
        validate_transition(
            _request(TicketState.ESCALATED, TicketState.READY, actor="agent:delivery-manager")
        )


def test_blocked_and_cancelled_require_human_actor_from_any_state() -> None:
    validate_transition(_request(TicketState.IN_PROGRESS, TicketState.BLOCKED))
    validate_transition(_request(TicketState.DONE, TicketState.CANCELLED))

    with pytest.raises(TransitionRejected):
        validate_transition(
            _request(TicketState.IN_PROGRESS, TicketState.BLOCKED, actor="agent:dev-1")
        )


def test_in_review_to_in_qa_requires_review_agent_or_human_actor() -> None:
    validate_transition(
        _request(TicketState.IN_REVIEW, TicketState.IN_QA, actor="agent:review-1")
    )
    validate_transition(_request(TicketState.IN_REVIEW, TicketState.IN_QA, actor="human:alice"))

    with pytest.raises(TransitionRejected):
        validate_transition(
            _request(TicketState.IN_REVIEW, TicketState.IN_QA, actor="agent:dev-1")
        )


def test_bounced_to_in_qa_is_a_human_only_override() -> None:
    validate_transition(_request(TicketState.BOUNCED, TicketState.IN_QA, actor="human:alice"))

    with pytest.raises(TransitionRejected):
        validate_transition(
            _request(TicketState.BOUNCED, TicketState.IN_QA, actor="agent:review-1")
        )


def test_human_actor_detection() -> None:
    from api.domain.state_machine import is_human_actor

    assert is_human_actor("human:alice")
    assert not is_human_actor("agent:dev-1")
    assert not is_human_actor("system")
