"""Product Planner agent (SPEC-102): approved idea -> epics + TaskSpec[], or
questions[] when under-specified. First real LangGraph adoption in this repo
(docs/06-tech-stack.md) — a single-node StateGraph, no PostgresSaver checkpointing
yet (nothing to resume across with one node; revisit when T-104+ chains multiple
agents into a real multi-step graph).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from llm_router import route
from schemas import PlannerPlan, PlannerQuestions

from orchestrator.api_client import ApiClient
from orchestrator.json_utils import extract_json_object
from orchestrator.prompt_version import parse_prompt_version

_REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_PLANNER_PROMPT_PATH = _REPO_ROOT / "prompts" / "planner.md"
_MAX_TOKENS = 4000
_PLANNER_ROLE = "planner"


class _PlannerState(TypedDict):
    system_prompt: str
    user_message: str
    text: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float


def _call_planner(state: _PlannerState) -> _PlannerState:
    result = route(
        _PLANNER_ROLE,
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
    graph = StateGraph(_PlannerState)
    graph.add_node("planner", _call_planner)
    graph.set_entry_point("planner")
    graph.add_edge("planner", END)
    return graph.compile()


_GRAPH = _build_graph()


@dataclass(frozen=True)
class PlannerAgentResult:
    run_id: int
    status: str  # "planned" | "questions"
    plan: PlannerPlan | None = None
    questions: list[str] | None = None
    cost_usd: float = 0.0


def build_planner_prompt(idea_title: str, idea_description: str, idea_budget_usd: float) -> str:
    lines = [
        f"# Idea: {idea_title}",
        "",
        idea_description or "(no additional description provided)",
        "",
        f"Approved budget: ${idea_budget_usd:.2f}",
    ]
    return "\n".join(lines)


def _create_plan_tickets(api: ApiClient, ticket_id: str, plan: PlannerPlan, actor: str) -> None:
    epic_ticket_id_by_planner_id = {}
    for epic in plan.epics:
        created = api.create_ticket(
            ticket_type="epic",
            title=epic.title,
            parent_id=ticket_id,
            created_by=actor,
            budget_usd=epic.budget_usd,
            spec={"id": epic.id, "description": epic.description},
        )
        epic_ticket_id_by_planner_id[epic.id] = created["id"]

    for task in plan.tasks:
        parent_id = epic_ticket_id_by_planner_id.get(task.epic_id or "", ticket_id)
        api.create_ticket(
            ticket_type="task",
            title=task.title,
            parent_id=parent_id,
            created_by=actor,
            budget_usd=task.budget_usd,
            acceptance_criteria=[
                {"id": c.id, "description": c.description, "verification": c.verification}
                for c in task.acceptance_criteria
            ],
            spec=task.model_dump(),
        )


def run_planner_agent(
    *,
    ticket_id: str,
    idea_title: str,
    idea_description: str,
    idea_budget_usd: float,
    api: ApiClient,
    prompt_path: Path = DEFAULT_PLANNER_PROMPT_PATH,
) -> PlannerAgentResult:
    actor = f"agent:planner-{ticket_id}"
    system_prompt = prompt_path.read_text(encoding="utf-8")
    user_message = build_planner_prompt(idea_title, idea_description, idea_budget_usd)

    run = api.create_agent_run(
        ticket_id,
        agent_role="planner",
        model="claude-opus-4-8",
        prompt_version=parse_prompt_version(system_prompt),
    )
    run_id = run["id"]

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
    final_state = cast(_PlannerState, raw_state)
    parsed = extract_json_object(final_state["text"])

    api.complete_agent_run(
        ticket_id,
        run_id,
        status="completed",
        tokens_in=final_state["tokens_in"],
        tokens_out=final_state["tokens_out"],
        cost_usd=final_state["cost_usd"],
    )

    if "questions" in parsed:
        questions = PlannerQuestions.model_validate(parsed)
        api.append_event(
            ticket_id,
            actor=actor,
            kind="message",
            payload={"conclusion": "planner_questions", "questions": questions.questions},
        )
        api.transition(ticket_id, to_state="escalated", actor=actor)
        return PlannerAgentResult(
            run_id=run_id,
            status="questions",
            questions=questions.questions,
            cost_usd=final_state["cost_usd"],
        )

    plan = PlannerPlan.model_validate(parsed)
    _create_plan_tickets(api, ticket_id, plan, actor)
    return PlannerAgentResult(
        run_id=run_id, status="planned", plan=plan, cost_usd=final_state["cost_usd"]
    )
