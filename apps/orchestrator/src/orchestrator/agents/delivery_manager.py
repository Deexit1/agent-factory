"""Delivery Manager agent (SPEC-103): assigns `ready` tasks to a capability-registry
profile in dependency order, respecting capacity, budgets, and repo locks. One
LangGraph node, single-node graph mirroring agents/planner.py (no PostgresSaver
checkpointing yet — same reasoning as the planner: nothing to resume across with one
node). One sonnet call per invocation decides for the WHOLE ready queue at once,
matching prompts/delivery-manager.md's batch input/output contract, not one call per
task — the prompt itself asks for cross-task prioritisation ("order by unblocking
power / budget efficiency / age"), which needs the whole queue in view at once.

Hard gates (dependencies done, budget vs spend, profile/repo capacity) are enforced
in apps/api, not here — this agent can propose an invalid assignment and the API
will refuse it (SPEC-103 AC4); this module just has to handle that refusal
gracefully instead of crashing.

T-105 (SPEC-104) adds real skill-matching: a task's TaskSpec.required_skills is
matched against each profile's `skills` in Python, before capacity is even checked
and before the LLM ever sees the task — a task with no matching profile is never
proposed to the model at all, distinct from the existing "no free capacity"
human_only path. Skill fit is a routing-quality concern this agent applies, not a
hard apps/api gate like the others above.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict, cast

import httpx
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from llm_router import route

from orchestrator.api_client import ApiClient
from orchestrator.capability_registry import CapabilityRegistry, load_registry
from orchestrator.json_utils import extract_json_object

_REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_DM_PROMPT_PATH = _REPO_ROOT / "prompts" / "delivery-manager.md"
_MAX_TOKENS = 4000
_DM_ROLE = "delivery-manager"
DM_ACTOR = "agent:delivery-manager"


class _DMState(TypedDict):
    system_prompt: str
    user_message: str
    text: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float


def _call_delivery_manager(state: _DMState) -> _DMState:
    result = route(
        _DM_ROLE,
        system=state["system_prompt"],
        messages=[{"role": "user", "content": state["user_message"]}],
        max_tokens=_MAX_TOKENS,
    )
    return {
        **state,
        "text": result.text,
        "model": result.model,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "cost_usd": result.cost_usd,
    }


def _build_graph() -> CompiledStateGraph:
    graph = StateGraph(_DMState)
    graph.add_node("delivery_manager", _call_delivery_manager)
    graph.set_entry_point("delivery_manager")
    graph.add_edge("delivery_manager", END)
    return graph.compile()


_GRAPH = _build_graph()


@dataclass(frozen=True)
class AssignmentOutcome:
    ticket_id: str
    decision: str  # "assigned" | "refused" | "deferred" | "human_only"
    profile: str | None
    reason: str


@dataclass(frozen=True)
class DeliveryManagerResult:
    outcomes: list[AssignmentOutcome] = field(default_factory=list)
    cost_usd: float = 0.0


def _profile_has_capacity(
    profile_id: str, registry: CapabilityRegistry, utilisation: dict[str, dict[str, Any]]
) -> bool:
    profile = registry.profiles.get(profile_id)
    row = utilisation.get(profile_id)
    if profile is None or row is None:
        return False
    return int(row["in_progress_count"]) < profile.max_parallel


def _skill_matching_profile_ids(
    registry: CapabilityRegistry, required_skills: list[str]
) -> list[str]:
    """A task with no required_skills matches any profile (today's un-tagged tasks
    keep working); otherwise a profile matches if it has ANY of the required skills
    — not all, since a profile's skill list is its full capability set, not a
    checklist a task must exhaust."""
    if not required_skills:
        return list(registry.profiles)
    required = set(required_skills)
    return [
        profile_id
        for profile_id, profile in registry.profiles.items()
        if required & set(profile.skills)
    ]


def _eligible_profile_ids(
    candidate_ids: list[str],
    registry: CapabilityRegistry,
    utilisation: dict[str, dict[str, Any]],
    prior_assignee: str | None,
) -> list[str]:
    """Every skill-matching candidate with free capacity, computed here in Python
    (not left to the LLM) so it can never propose an ineligible profile. The task's
    own prior assignee (a requeued/reassignment case) is deprioritised, not
    excluded, when an alternative exists — matching the prompt's "propose a
    different profile" rule."""
    eligible = [
        profile_id
        for profile_id in candidate_ids
        if _profile_has_capacity(profile_id, registry, utilisation)
    ]
    if prior_assignee in eligible and len(eligible) > 1:
        eligible = [p for p in eligible if p != prior_assignee] + [prior_assignee]
    return eligible


def _build_user_message(
    tasks: list[dict[str, Any]],
    eligible_by_task: dict[str, list[str]],
    registry: CapabilityRegistry,
) -> str:
    lines = ["## Ready tasks"]
    for task in tasks:
        lines.append(
            f"- id: {task['id']}\n"
            f"  title: {task['title']}\n"
            f"  budget_usd: {task.get('budget_usd')}\n"
            f"  eligible_profiles: {eligible_by_task[task['id']]}"
        )
    lines.append("\n## Capability registry (only eligible_profiles above are assignable)")
    for profile in registry.profiles.values():
        lines.append(
            f"- {profile.id}: skills={list(profile.skills)}, max_parallel={profile.max_parallel}"
        )
    return "\n".join(lines)


def _record_decision(
    api: ApiClient, ticket_id: str, *, decision: str, reason: str, considered: list[str]
) -> None:
    api.append_event(
        ticket_id,
        actor=DM_ACTOR,
        kind="assignment",
        payload={"decision": decision, "reason": reason, "considered": considered},
    )


def run_delivery_manager_agent(
    *,
    api: ApiClient,
    registry: CapabilityRegistry | None = None,
    prompt_path: Path = DEFAULT_DM_PROMPT_PATH,
) -> DeliveryManagerResult:
    registry = registry if registry is not None else load_registry()
    ready_tasks = api.list_tickets(state="ready", ticket_type="task")
    if not ready_tasks:
        return DeliveryManagerResult()

    utilisation = {row["profile"]: row for row in api.utilisation()}

    outcomes: list[AssignmentOutcome] = []
    eligible_by_task: dict[str, list[str]] = {}
    llm_tasks: list[dict[str, Any]] = []
    for task in ready_tasks:
        required_skills = [str(s) for s in (task.get("spec") or {}).get("required_skills", [])]
        skill_matches = _skill_matching_profile_ids(registry, required_skills)
        if not skill_matches:
            reason = "no profile has the required skills"
            outcomes.append(AssignmentOutcome(task["id"], "human_only", None, reason))
            _record_decision(api, task["id"], decision="human_only", reason=reason, considered=[])
            continue

        eligible = _eligible_profile_ids(
            skill_matches, registry, utilisation, task.get("assignee_agent")
        )
        if not eligible:
            reason = "no eligible profile has free capacity"
            outcomes.append(AssignmentOutcome(task["id"], "human_only", None, reason))
            _record_decision(api, task["id"], decision="human_only", reason=reason, considered=[])
            continue
        eligible_by_task[task["id"]] = eligible
        llm_tasks.append(task)

    if not llm_tasks:
        return DeliveryManagerResult(outcomes=outcomes)

    system_prompt = prompt_path.read_text(encoding="utf-8")
    user_message = _build_user_message(llm_tasks, eligible_by_task, registry)

    raw_state = _GRAPH.invoke(
        {
            "system_prompt": system_prompt,
            "user_message": user_message,
            "text": "",
            "model": "",
            "tokens_in": 0,
            "tokens_out": 0,
            "cost_usd": 0.0,
        }
    )
    final_state = cast(_DMState, raw_state)
    parsed = extract_json_object(final_state["text"])

    # One batch LLM call decides for every considered task; agent_runs has no "not
    # tied to a single ticket" concept, so the whole call's cost is attributed to the
    # first considered task rather than inventing a proportional split — a disclosed
    # simplification, not a real multi-ticket cost model.
    run = api.create_agent_run(
        llm_tasks[0]["id"], agent_role="delivery-manager", model=final_state["model"]
    )
    api.complete_agent_run(
        llm_tasks[0]["id"],
        run["id"],
        status="completed",
        tokens_in=final_state["tokens_in"],
        tokens_out=final_state["tokens_out"],
        cost_usd=final_state["cost_usd"],
    )

    assignments = {a["task_id"]: a for a in parsed.get("assignments", [])}
    deferred = {d["task_id"]: d for d in parsed.get("deferred", [])}

    for task in llm_tasks:
        task_id = task["id"]
        considered = eligible_by_task[task_id]

        if task_id in assignments:
            proposal = assignments[task_id]
            profile = proposal["profile"]
            reason = str(proposal.get("reason", ""))
            alternatives = [str(a) for a in proposal.get("alternatives", [])]
            if profile not in considered:
                # apps/api has no hard gate for skill-match (it's a DM-side routing
                # filter, not a safety invariant like budget/capacity) — a profile
                # with free capacity but the wrong skills would otherwise sail
                # through the API unchecked. Catch it here instead of ever calling
                # transition() with a profile this run never considered eligible.
                decision = "refused"
                reason = f"{reason} (rejected: {profile!r} was not in the eligible set)"
            else:
                try:
                    api.transition(task_id, to_state="in_progress", assignee_agent=profile)
                    decision = "assigned"
                except httpx.HTTPStatusError as exc:
                    decision = "refused"
                    reason = f"{reason} (refused: {exc.response.text})"
            outcomes.append(AssignmentOutcome(task_id, decision, profile, reason))
            _record_decision(
                api,
                task_id,
                decision=decision,
                reason=reason,
                considered=sorted(set(considered) | set(alternatives)),
            )
            continue

        reason = (
            str(deferred[task_id].get("reason", ""))
            if task_id in deferred
            else ("not addressed by delivery manager response")
        )
        outcomes.append(AssignmentOutcome(task_id, "deferred", None, reason))
        _record_decision(api, task_id, decision="deferred", reason=reason, considered=considered)

    return DeliveryManagerResult(outcomes=outcomes, cost_usd=final_state["cost_usd"])
