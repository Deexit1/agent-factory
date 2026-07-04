from dataclasses import dataclass

from fastapi import Header

# Stub auth: a real user header today, OIDC/SSO wired up in T-008 (SPEC-006).
Role = str  # "admin" | "approver" | "viewer"


@dataclass(frozen=True)
class ActorContext:
    actor: str
    role: Role


def get_actor_context(
    x_actor: str = Header(default="human:anonymous", alias="X-Actor"),
    x_actor_role: str = Header(default="viewer", alias="X-Actor-Role"),
) -> ActorContext:
    return ActorContext(actor=x_actor, role=x_actor_role)
