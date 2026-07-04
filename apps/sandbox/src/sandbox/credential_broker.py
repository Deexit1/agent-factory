import json
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from sandbox.config import state_dir_for


@dataclass(frozen=True)
class Credential:
    ticket_id: str
    token: str
    issued_at: float
    allowed_ref: str


def _credential_path(ticket_id: str) -> Path:
    return state_dir_for(ticket_id) / "credential.json"


def issue(ticket_id: str) -> Credential:
    """Mint a short-lived token scoped to push refs/heads/agent/<ticket_id> only.

    Stands in for a real Vault + GitHub App integration: same issue/revoke shape,
    but the token is a local secret for a local git remote (Phase 1 only) rather
    than a real GitHub credential. Swap this module out, not its callers, when
    real Vault/GitHub App wiring lands.
    """
    credential = Credential(
        ticket_id=ticket_id,
        token=secrets.token_urlsafe(32),
        issued_at=time.time(),
        allowed_ref=f"refs/heads/agent/{ticket_id}",
    )
    path = _credential_path(ticket_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(credential)))
    return credential


def get(ticket_id: str) -> Credential | None:
    path = _credential_path(ticket_id)
    if not path.exists():
        return None
    return Credential(**json.loads(path.read_text()))


def revoke(ticket_id: str) -> None:
    _credential_path(ticket_id).unlink(missing_ok=True)
