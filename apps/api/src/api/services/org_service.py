import os
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.db.models import Org, OrgInvite, OrgInviteStatus, OrgMember, UserRole
from api.repositories import org_repository as repo
from api.repositories import tos_repository
from api.tenancy import DEFAULT_ORG_ID


class OrgNotFound(Exception):
    def __init__(self, org_id: str) -> None:
        self.org_id = org_id
        super().__init__(f"org {org_id} not found")


class InviteNotFound(Exception):
    pass


def _admin_emails() -> set[str]:
    return {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}


def create_org(session: Session, *, name: str, owner_email: str, tos_version: str) -> Org:
    """T-206 (SPEC-206 AC3): every org's creation transactionally records its owner's
    ToS acceptance — an org can't exist before wizard step 1, so acceptance can't
    predate it either."""
    org = repo.create_org(session, name=name)
    repo.create_membership(session, org_id=org.id, user_email=owner_email, role=UserRole.OWNER)
    tos_repository.record_tos_acceptance(
        session,
        org_id=org.id,
        accepted_by=owner_email,
        tos_version=tos_version,
        accepted_at=datetime.now(UTC),
    )
    session.commit()
    return org


def list_orgs_for_user(session: Session, *, user_email: str) -> list[Org]:
    return repo.list_orgs_for_user(session, user_email=user_email)


def ensure_default_org_membership(session: Session, *, user_email: str) -> OrgMember:
    """Login-time bootstrap (T-008 behavior preserved): a user with no org
    membership anywhere gets auto-joined into the seeded default org —
    ADMIN_EMAILS -> owner, else viewer. Users who arrive via an accepted invite
    already have a membership by the time they first log in, so this is a no-op
    for them (list_orgs_for_user already returns something).

    Two concurrent first-logins for the same email (e.g. two tabs, or two parallel
    Playwright workers hitting the same fixed test email) can both pass the
    "no existing membership" check before either commits; the loser's INSERT hits
    `uq_org_members_org_user`, so we catch that and re-fetch the winner's row
    instead of 500ing — same pattern as `user_service.get_or_create_user`."""
    existing = repo.list_orgs_for_user(session, user_email=user_email)
    if existing:
        first_org_member = repo.get_membership(
            session, org_id=existing[0].id, user_email=user_email
        )
        assert first_org_member is not None
        return first_org_member

    role = UserRole.OWNER if user_email.lower() in _admin_emails() else UserRole.VIEWER
    member: OrgMember | None
    try:
        member = repo.create_membership(
            session, org_id=DEFAULT_ORG_ID, user_email=user_email, role=role
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        member = repo.get_membership(session, org_id=DEFAULT_ORG_ID, user_email=user_email)
    assert member is not None
    return member


def resolve_login_membership(session: Session, *, user_email: str) -> OrgMember:
    """Picks which org a login lands in when none is explicitly requested: the
    user's first org membership (auto-joining the default org if they have none at
    all yet). Multi-org users who want a DIFFERENT org use the org switcher
    (POST /auth/switch-org) after landing — a full interactive "choose an org at
    login" flow is deliberately out of scope (disclosed in tasks/CHANGELOG.md)."""
    orgs = repo.list_orgs_for_user(session, user_email=user_email)
    if not orgs:
        return ensure_default_org_membership(session, user_email=user_email)
    member = repo.get_membership(session, org_id=orgs[0].id, user_email=user_email)
    assert member is not None
    return member


def get_or_create_dev_membership(
    session: Session, *, org_id: str, user_email: str, role_override: UserRole | None
) -> OrgMember:
    """Dev-login only (AUTH_DEV_MODE) — never used by the real OIDC path. Mirrors
    the old get_or_create_user's role_override convenience, now at the membership
    level: first login into an org wins, a later dev-login for the same (org,
    email) pair is a no-op regardless of the role param.

    Same concurrent-first-login race as `ensure_default_org_membership` above —
    two dev-login calls for the same (org_id, email) racing past the initial
    `get_membership` check both attempt the INSERT; the loser's hits
    `uq_org_members_org_user` and is caught here rather than 500ing. Real-world
    trigger: Playwright's parallel workers all logging in as the same fixed test
    email in a `beforeEach` (e2e/board.spec.ts)."""
    existing = repo.get_membership(session, org_id=org_id, user_email=user_email)
    if existing is not None:
        return existing
    role = role_override or (
        UserRole.OWNER if user_email.lower() in _admin_emails() else UserRole.VIEWER
    )
    member: OrgMember | None
    try:
        member = repo.create_membership(session, org_id=org_id, user_email=user_email, role=role)
        session.commit()
    except IntegrityError:
        session.rollback()
        member = repo.get_membership(session, org_id=org_id, user_email=user_email)
        assert member is not None
    return member


def invite_member(
    session: Session, *, org_id: str, email: str, role: UserRole, invited_by: str
) -> OrgInvite:
    invite = repo.create_invite(
        session, org_id=org_id, email=email, role=role, invited_by=invited_by
    )
    session.commit()
    return invite


def accept_invite(session: Session, *, token: str, accepting_email: str) -> OrgMember:
    invite = repo.get_invite_by_token(session, token)
    if (
        invite is None
        or invite.status != OrgInviteStatus.PENDING
        or invite.email.lower() != accepting_email.lower()
    ):
        raise InviteNotFound(token)
    member = repo.accept_invite(session, invite)
    session.commit()
    return member


def list_members(session: Session, *, org_id: str) -> list[OrgMember]:
    return repo.list_members(session, org_id=org_id)


def accept_tos(session: Session, *, org_id: str, accepted_by: str, tos_version: str) -> None:
    """T-206 (SPEC-206 AC3): re-acceptance for an existing org whose latest recorded
    version is stale (bumped tos.CURRENT_TOS_VERSION). Idempotent per (org, version) —
    the unique constraint means re-accepting an already-accepted version is a no-op
    error the caller doesn't need to special-case, since ticket_service only ever
    checks "is the latest version current", not "how many times was it accepted"."""
    existing = tos_repository.get_latest_tos_acceptance(session, org_id=org_id)
    if existing is not None and existing.tos_version == tos_version:
        return
    tos_repository.record_tos_acceptance(
        session,
        org_id=org_id,
        accepted_by=accepted_by,
        tos_version=tos_version,
        accepted_at=datetime.now(UTC),
    )
    session.commit()


__all__ = [
    "OrgNotFound",
    "InviteNotFound",
    "create_org",
    "list_orgs_for_user",
    "ensure_default_org_membership",
    "resolve_login_membership",
    "get_or_create_dev_membership",
    "invite_member",
    "accept_invite",
    "list_members",
    "accept_tos",
]
