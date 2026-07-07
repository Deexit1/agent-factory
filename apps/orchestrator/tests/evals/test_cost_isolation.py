"""T-108 AC3: eval runs must never write to agent_runs/cost_ledger (ticket
unit-economics is a real-work-only metric). Verified structurally rather than by
actually running an eval case against a live API: every eval scorer here calls a real
Anthropic model (llm_router.route), so a DB-round-trip integration test would be
flaky under this environment's recurring provider-credit exhaustion (see
tasks/CHANGELOG.md) for a fact that's true by construction, not by luck — nothing
under orchestrator/evals imports the ticket API client or the agent-run repository, so
there is no code path for an eval run to create an AgentRun/CostLedgerEntry row. This
test fails loudly if that ever changes."""

import ast
from pathlib import Path

_EVALS_DIR = Path(__file__).resolve().parents[2] / "src" / "orchestrator" / "evals"
_FORBIDDEN_MODULES = {
    "orchestrator.api_client",
    "api.repositories.agent_run_repository",
    "api.services.agent_run_service",
}


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_no_eval_module_imports_the_ticket_api_client_or_agent_run_repository() -> None:
    eval_files = sorted(_EVALS_DIR.glob("*.py"))
    assert eval_files, f"expected eval modules under {_EVALS_DIR}"

    offenders: dict[str, set[str]] = {}
    for path in eval_files:
        imported = _imported_modules(path.read_text(encoding="utf-8"))
        hit = imported & _FORBIDDEN_MODULES
        if hit:
            offenders[path.name] = hit

    assert not offenders, (
        "eval modules must never write ticket cost data (AC3) - found forbidden "
        f"imports: {offenders}"
    )
