import hmac
import os
import time
from dataclasses import dataclass

import jwt
from fastapi import Header, HTTPException

from api.db.models import UserRole
from api.tenancy import DEFAULT_ORG_ID

Role = str

SESSION_ALG = "HS256"
SESSION_TTL_SECONDS = 60 * 60 * 12  # 12h
SERVICE_ACTOR = "system"


@dataclass(frozen=True)
class ActorContext:
    actor: str
    role: Role
    org_id: str = DEFAULT_ORG_ID


class OidcNotConfigured(Exception):
    pass


def session_secret() -> str:
    secret = os.environ.get("SESSION_JWT_SECRET", "")
    if not secret:
        raise RuntimeError("SESSION_JWT_SECRET must be set to issue or verify session tokens")
    return secret


def mint_session_token(email: str, role: UserRole) -> str:
    now = int(time.time())
    payload = {"sub": email, "role": role.value, "iat": now, "exp": now + SESSION_TTL_SECONDS}
    return jwt.encode(payload, session_secret(), algorithm=SESSION_ALG)


def _verify_session_token(token: str) -> ActorContext:
    try:
        payload = jwt.decode(token, session_secret(), algorithms=[SESSION_ALG])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid or expired session token") from exc
    return ActorContext(actor=f"human:{payload['sub']}", role=payload["role"])


def _service_token() -> str:
    return os.environ.get("AGENT_FACTORY_SERVICE_TOKEN", "")


def get_actor_context(
    authorization: str | None = Header(default=None),
) -> ActorContext:
    """Every route except /health, /webhooks/* and /auth/* depends on this (SPEC-006 AC1).

    Two ways in: the shared service token (orchestrator/sandbox, full trust, role=admin)
    or a session JWT minted at OIDC login / dev-login. Anything else is 401.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()

    service_token = _service_token()
    if service_token and hmac.compare_digest(token, service_token):
        return ActorContext(actor=SERVICE_ACTOR, role="admin")

    return _verify_session_token(token)
