"""Review agent (SPEC-105): first-pass code review between dev and QA. One LangGraph
node, single-node graph mirroring agents/planner.py and agents/delivery_manager.py (no
PostgresSaver checkpointing yet — same reasoning: nothing to resume across with one
node). Takes a PR diff + TaskSpec + style guide + (optionally) Semgrep findings, and
produces a `ReviewResult` (approve/block + comments + scope_violations).

Real Semgrep integration (parsing CI's actual output back into this agent) is
deliberately out of scope here — `semgrep_findings` is an injectable string
parameter (empty by default), mirroring how `run_delivery_manager_agent` takes an
injectable `registry`. This agent has no auto-dispatch trigger, matching every other
agent in this repo (Planner, Delivery Manager, dev agent) — it's a callable entry
point, invoked by tests/an ops script, not triggered automatically on ticket
transitions.

Verdict handling: approve -> in_qa; block -> bounced (bounce_count shared with QA
failures). The IN_REVIEW -> IN_QA transition is now a real apps/api gate (only a
review-agent or human actor may request it) — this agent can't accidentally be
bypassed by some other actor skipping review.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

import httpx
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from llm_router import ProviderCredential, route
from schemas import ReviewResult, TaskSpec

from orchestrator.api_client import ApiClient
from orchestrator.dispatch_gate import resolve_dispatch
from orchestrator.github_client import GitHubClient, PullRequest
from orchestrator.json_utils import extract_json_object
from orchestrator.prompt_version import parse_prompt_version

_REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_REVIEW_PROMPT_PATH = _REPO_ROOT / "prompts" / "review-agent.md"
_STYLE_GUIDE_PATH = _REPO_ROOT / "docs" / "07-conventions.md"
_MAX_TOKENS = 4000
_REVIEW_ROLE = "review"
REVIEW_ACTOR = "agent:review"


class _ReviewState(TypedDict):
    system_prompt: str
    user_message: str
    credentials: list[ProviderCredential]
    text: str
    model: str
    provider: str
    tokens_in: int
    tokens_out: int
    cost_usd: float


def _call_review_agent(state: _ReviewState) -> _ReviewState:
    result = route(
        _REVIEW_ROLE,
        credentials=state["credentials"],
        system=state["system_prompt"],
        messages=[{"role": "user", "content": state["user_message"]}],
        max_tokens=_MAX_TOKENS,
    )
    return {
        **state,
        "text": result.text,
        "model": result.model,
        "provider": result.provider,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "cost_usd": result.cost_usd,
    }


def _build_graph() -> CompiledStateGraph:
    graph = StateGraph(_ReviewState)
    graph.add_node("review", _call_review_agent)
    graph.set_entry_point("review")
    graph.add_edge("review", END)
    return graph.compile()


_GRAPH = _build_graph()


@dataclass(frozen=True)
class ReviewAgentResult:
    verdict: str  # "approve" | "block" | "blocked" (dispatch blocked, T-202)
    result: ReviewResult | None
    cost_usd: float
    transitioned: bool  # False when the API refused the transition (e.g. auto-escalated)
    reason: str | None = None


def _build_user_message(
    *, diff: str, task_spec: TaskSpec, style_guide: str, semgrep_findings: str
) -> str:
    lines = [
        "## TaskSpec",
        f"id: {task_spec.id}",
        f"title: {task_spec.title}",
        f"context: {task_spec.context}",
        "acceptance_criteria:",
    ]
    for ac in task_spec.acceptance_criteria:
        lines.append(f"- [{ac.id}] {ac.description} (verify: {ac.verification})")
    lines.append("")
    lines.append("## PR diff")
    lines.append(diff)
    lines.append("")
    lines.append("## Style guide (docs/07-conventions.md)")
    lines.append(style_guide)
    lines.append("")
    lines.append("## Semgrep findings")
    lines.append(semgrep_findings or "(none provided)")
    return "\n".join(lines)


def run_review_agent(
    *,
    ticket_id: str,
    task_spec: TaskSpec,
    pr: PullRequest,
    api: ApiClient,
    github: GitHubClient,
    semgrep_findings: str = "",
    prompt_path: Path = DEFAULT_REVIEW_PROMPT_PATH,
) -> ReviewAgentResult:
    ticket = api.get_ticket(ticket_id)
    org_id = ticket["org_id"]
    decision = resolve_dispatch(api, org_id=org_id, agent_role=_REVIEW_ROLE)
    if not decision.allowed:
        api.append_event(
            ticket_id,
            actor=REVIEW_ACTOR,
            kind="message",
            payload={"conclusion": "dispatch_blocked", "reason": decision.reason},
        )
        return ReviewAgentResult(
            verdict="blocked", result=None, cost_usd=0.0, transitioned=False, reason=decision.reason
        )

    system_prompt = prompt_path.read_text(encoding="utf-8")
    diff = github.get_pr_diff(pr)
    style_guide = _STYLE_GUIDE_PATH.read_text(encoding="utf-8")
    user_message = _build_user_message(
        diff=diff, task_spec=task_spec, style_guide=style_guide, semgrep_findings=semgrep_findings
    )

    raw_state = _GRAPH.invoke(
        {
            "system_prompt": system_prompt,
            "user_message": user_message,
            "credentials": decision.credentials,
            "text": "",
            "model": "",
            "provider": "",
            "tokens_in": 0,
            "tokens_out": 0,
            "cost_usd": 0.0,
        }
    )
    final_state = cast(_ReviewState, raw_state)
    parsed = extract_json_object(final_state["text"])
    result = ReviewResult.model_validate(parsed)

    run = api.create_agent_run(
        ticket_id,
        agent_role="review",
        model=final_state["model"],
        prompt_version=parse_prompt_version(system_prompt),
    )
    api.complete_agent_run(
        ticket_id,
        run["id"],
        status="completed",
        tokens_in=final_state["tokens_in"],
        tokens_out=final_state["tokens_out"],
        cost_usd=final_state["cost_usd"],
        provider=final_state["provider"],
    )

    if result.verdict == "approve":
        github.post_comment(pr, "Review agent: approved.")
        to_state = "in_qa"
    else:
        comment_lines = [f"- {c.file}:{c.line}: {c.comment}" for c in result.comments]
        scope_lines = [f"- {f}" for f in result.scope_violations]
        body = "Review agent: blocked.\n\n" + "\n".join(comment_lines)
        if scope_lines:
            body += "\n\nOut-of-scope files:\n" + "\n".join(scope_lines)
        github.post_comment(pr, body)
        to_state = "bounced"

    transitioned = True
    try:
        api.transition(ticket_id, to_state=to_state, actor=REVIEW_ACTOR)
    except httpx.HTTPStatusError:
        # A block at max bounces means apps/api already auto-escalated the ticket
        # server-side before refusing this request — nothing to retry, just record
        # what happened instead of crashing (mirrors the Delivery Manager's
        # refusal-handling pattern).
        transitioned = False

    api.append_event(
        ticket_id,
        actor=REVIEW_ACTOR,
        kind="review",
        payload={
            "verdict": result.verdict,
            "comments": [c.model_dump() for c in result.comments],
            "scope_violations": result.scope_violations,
            "transitioned": transitioned,
        },
    )

    return ReviewAgentResult(
        verdict=result.verdict,
        result=result,
        cost_usd=final_state["cost_usd"],
        transitioned=transitioned,
    )
