from dataclasses import dataclass

from api.db.models import TicketState

MAX_BOUNCES = 3

_BASE_TRANSITIONS: dict[TicketState, set[TicketState]] = {
    TicketState.PROPOSED: {TicketState.EXEC_REVIEW},
    TicketState.EXEC_REVIEW: {TicketState.AWAITING_HUMAN_GO},
    TicketState.AWAITING_HUMAN_GO: {TicketState.APPROVED, TicketState.CANCELLED},
    TicketState.APPROVED: {TicketState.PLANNING},
    TicketState.PLANNING: {TicketState.READY, TicketState.ESCALATED},
    TicketState.READY: {TicketState.IN_PROGRESS},
    TicketState.IN_PROGRESS: {TicketState.IN_REVIEW, TicketState.ESCALATED},
    TicketState.IN_REVIEW: {TicketState.IN_QA, TicketState.BOUNCED, TicketState.ESCALATED},
    TicketState.IN_QA: {TicketState.DONE, TicketState.BOUNCED, TicketState.ESCALATED},
    TicketState.BOUNCED: {TicketState.IN_PROGRESS, TicketState.IN_QA},
    TicketState.ESCALATED: {TicketState.IN_PROGRESS, TicketState.PLANNING, TicketState.READY},
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
    # Idea-plan sanity gates (SPEC-102), computed by the service layer from the idea's
    # descendant epic/task tickets — state_machine.py stays a pure function, no I/O.
    plan_task_count: int = 0
    plan_has_cycle: bool = False
    plan_child_budget_total: float = 0.0
    plan_has_budget_approval: bool = False
    # Delivery Manager assignment gates (SPEC-103), computed by the service layer —
    # state_machine.py stays a pure function, no I/O.
    deps_done: bool = True
    spent_usd: float = 0.0
    assignee_agent: str | None = None
    profile_at_capacity: bool = False
    repo_at_capacity: bool = False


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


def _check_bounce_guard(request: TransitionRequest) -> None:
    if request.bounce_count >= MAX_BOUNCES:
        raise TransitionRejected(
            f"bounce_count reached the max ({MAX_BOUNCES}); "
            "ticket must be escalated, not bounced again"
        )


def _check_guard(request: TransitionRequest) -> None:
    if request.from_state is TicketState.APPROVED and request.to_state is TicketState.PLANNING:
        if not request.budget_usd or request.budget_usd <= 0:
            raise TransitionRejected("idea must have a human-approved budget before planning")

    if request.from_state is TicketState.PLANNING and request.to_state is TicketState.READY:
        # Per-task acceptance_criteria/verification is already enforced at task-creation
        # time (schema + CreateTicketRequest validators) — the ticket-level
        # acceptance_criteria_count only matters for non-idea tickets that reach this
        # transition directly (e.g. a task with no plan of its own).
        if request.acceptance_criteria_count == 0 and request.plan_task_count == 0:
            raise TransitionRejected("plan has no tasks; nothing to make ready")
        if request.plan_has_cycle:
            raise TransitionRejected("task dependency graph contains a cycle")
        if request.budget_usd and request.plan_child_budget_total > request.budget_usd:
            raise TransitionRejected(
                f"sum of task budgets (${request.plan_child_budget_total:.2f}) exceeds "
                f"the idea's budget (${request.budget_usd:.2f})"
            )
        if request.plan_task_count > 0 and not request.plan_has_budget_approval:
            raise TransitionRejected("idea plan requires an approved budget gate before ready")

    if request.from_state is TicketState.PLANNING and request.to_state is TicketState.ESCALATED:
        if not is_human_actor(request.actor) and not request.actor.startswith("agent:planner"):
            raise TransitionRejected(
                "only the planner or a human may escalate an under-specified idea"
            )

    if request.from_state is TicketState.ESCALATED and request.to_state is TicketState.PLANNING:
        if not is_human_actor(request.actor):
            raise TransitionRejected("only a human may return an escalated idea to planning")

    if request.from_state is TicketState.ESCALATED and request.to_state is TicketState.READY:
        if not is_human_actor(request.actor):
            raise TransitionRejected(
                "only a human may requeue an escalated task for reassignment"
            )

    if request.from_state is TicketState.READY and request.to_state is TicketState.IN_PROGRESS:
        if not request.budget_usd or request.budget_usd <= 0:
            raise TransitionRejected("budget_usd must be > 0 before starting work")
        if request.spent_usd >= request.budget_usd:
            raise TransitionRejected(
                f"task already spent its budget (${request.spent_usd:.2f} of "
                f"${request.budget_usd:.2f}); cannot be (re)assigned"
            )
        if not request.deps_done:
            raise TransitionRejected("this task's dependencies are not done yet")
        if request.assignee_agent is not None:
            if request.profile_at_capacity:
                raise TransitionRejected(
                    f"profile {request.assignee_agent!r} is at max_parallel capacity"
                )
            if request.repo_at_capacity:
                raise TransitionRejected("repo is at its concurrency limit")

    if request.from_state is TicketState.IN_QA and request.to_state is TicketState.DONE:
        if request.bounce_count >= MAX_BOUNCES:
            raise TransitionRejected(
                f"bounce_count reached the max ({MAX_BOUNCES}); ticket must be escalated, not done"
            )

    if request.to_state is TicketState.BOUNCED and request.from_state in (
        TicketState.IN_QA,
        TicketState.IN_REVIEW,
    ):
        _check_bounce_guard(request)

    if request.from_state is TicketState.ESCALATED and request.to_state is TicketState.IN_PROGRESS:
        if not is_human_actor(request.actor):
            raise TransitionRejected("only a human may return an escalated ticket to dev")

    if request.from_state is TicketState.IN_REVIEW and request.to_state is TicketState.IN_QA:
        if not is_human_actor(request.actor) and not request.actor.startswith("agent:review"):
            raise TransitionRejected("only the review agent or a human may approve a PR into QA")

    if request.from_state is TicketState.BOUNCED and request.to_state is TicketState.IN_QA:
        if not is_human_actor(request.actor):
            raise TransitionRejected(
                "only a human may override a bounced ticket straight to QA"
            )
