"""T-203: the dev agent's PR branch naming convention, in one place.

Previously duplicated ad hoc as f"agent/{ticket_id}" in
apps/orchestrator/src/orchestrator/agents/dev.py and merge_queue.py. The new GitHub
webhook handler (github_webhook_service.py) needs the inverse (branch -> ticket_id), so
centralizing here avoids a third, independently-drifting copy.
"""

AGENT_BRANCH_PREFIX = "agent/"


def agent_branch_name(ticket_id: str) -> str:
    return f"{AGENT_BRANCH_PREFIX}{ticket_id}"


def ticket_id_from_branch(branch: str) -> str | None:
    if not branch.startswith(AGENT_BRANCH_PREFIX):
        return None
    ticket_id = branch.removeprefix(AGENT_BRANCH_PREFIX)
    return ticket_id or None
