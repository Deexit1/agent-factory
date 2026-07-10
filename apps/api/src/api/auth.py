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
IMPERSONATION_TTL_SECONDS = 60 * 15  # T-201 AC5: short-lived, re-request to continue
SERVICE_ACTOR = "system"


@dataclass(frozen=True)
class ActorContext:
    actor: str
    role: Role
    org_id: str = DEFAULT_ORG_ID
    is_platform_staff: bool = False
    # T-201 AC5: a "view as org" session — actor is `staff:{email}`, not
    # `human:{email}`, so state_machine.is_human_actor() correctly excludes it from
    # human-only gates (approve/reject etc.) — impersonation is for support visibility,
    # not for acting as if staff were a member of the org they're viewing.
    impersonating: bool = False


class OidcNotConfigured(Exception):
    pass


def session_secret() -> str:
    secret = os.environ.get("SESSION_JWT_SECRET", "")
    if not secret:
        raise RuntimeError("SESSION_JWT_SECRET must be set to issue or verify session tokens")
    return secret


def mint_session_token(
    email: str,
    *,
    org_id: str,
    role: UserRole,
    is_platform_staff: bool = False,
    impersonating: bool = False,
) -> str:
    now = int(time.time())
    ttl = IMPERSONATION_TTL_SECONDS if impersonating else SESSION_TTL_SECONDS
    payload = {
        "sub": email,
        "org_id": org_id,
        "role": role.value,
        "staff": is_platform_staff,
        "impersonating": impersonating,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, session_secret(), algorithm=SESSION_ALG)


def _verify_session_token(token: str) -> ActorContext:
    try:
        payload = jwt.decode(token, session_secret(), algorithms=[SESSION_ALG])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid or expired session token") from exc
    impersonating = payload.get("impersonating", False)
    actor_prefix = "staff" if impersonating else "human"
    return ActorContext(
        actor=f"{actor_prefix}:{payload['sub']}",
        role=payload["role"],
        org_id=payload["org_id"],
        is_platform_staff=payload.get("staff", False),
        impersonating=impersonating,
    )


def _service_token() -> str:
    return os.environ.get("AGENT_FACTORY_SERVICE_TOKEN", "")


def get_actor_context(
    authorization: str | None = Header(default=None),
    x_org_id: str | None = Header(default=None),
) -> ActorContext:
    """Every route except /health, /webhooks/* and /auth/* depends on this (SPEC-006 AC1).

    Two ways in: the shared service token (orchestrator/sandbox, full trust, role=owner)
    or a session JWT minted at OIDC login / dev-login. Anything else is 401.

    T-211: the service-token branch used to always resolve to DEFAULT_ORG_ID, which is
    why the orchestrator's agent dispatch could only ever act on that one seeded org
    (disclosed and deferred across T-201/T-202/T-206 — see tasks/CHANGELOG.md). It now
    honors an optional `X-Org-Id` header, trusted ONLY on this branch — a human's
    org_id is already embedded in their signed session JWT and this header is never
    consulted for that branch, so a human token can't spoof another org via it. Every
    existing service-token caller that doesn't send the header (tests, run_pilot.py)
    is unaffected — still defaults to DEFAULT_ORG_ID exactly as before.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()

    service_token = _service_token()
    if service_token and hmac.compare_digest(token, service_token):
        return ActorContext(actor=SERVICE_ACTOR, role="owner", org_id=x_org_id or DEFAULT_ORG_ID)

    return _verify_session_token(token)
