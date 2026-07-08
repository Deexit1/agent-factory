from schemas.branches import AGENT_BRANCH_PREFIX, agent_branch_name, ticket_id_from_branch


def test_agent_branch_name_uses_the_prefix() -> None:
    assert agent_branch_name("T-203") == "agent/T-203"
    assert agent_branch_name("T-203").startswith(AGENT_BRANCH_PREFIX)


def test_ticket_id_from_branch_is_the_inverse() -> None:
    assert ticket_id_from_branch("agent/T-203") == "T-203"


def test_ticket_id_from_branch_returns_none_for_a_non_agent_branch() -> None:
    assert ticket_id_from_branch("main") is None
    assert ticket_id_from_branch("feature/something") is None


def test_ticket_id_from_branch_returns_none_for_bare_prefix() -> None:
    assert ticket_id_from_branch("agent/") is None
