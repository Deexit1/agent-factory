import os

from sqlalchemy.orm import Session

from api.db.models import Org, OrgInvite, OrgInviteStatus, OrgMember, UserRole
from api.repositories import org_repository as repo
from api.tenancy import DEFAULT_ORG_ID


class OrgNotFound(Exception):
    def __init__(self, org_id: str) -> None:
        self.org_id = org_id
        super().__init__(f"org {org_id} not found")


class InviteNotFound(Exception):
    pass


def _admin_emails() -> set[str]:
    return {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}


def create_org(session: Session, *, name: str, owner_email: str) -> Org:
    org = repo.create_org(session, name=name)
    repo.create_membership(session, org_id=org.id, user_email=owner_email, role=UserRole.OWNER)
    session.commit()
    return org


def list_orgs_for_user(session: Session, *, user_email: str) -> list[Org]:
    return repo.list_orgs_for_user(session, user_email=user_email)


def ensure_default_org_membership(session: Session, *, user_email: str) -> OrgMember:
    """Login-time bootstrap (T-008 behavior preserved): a user with no org
    membership anywhere gets auto-joined into the seeded default org —
    ADMIN_EMAILS -> owner, else viewer. Users who arrive via an accepted invite
    already have a membership by the time they first log in, so this is a no-op
    for them (list_orgs_for_user already returns something)."""
    existing = repo.list_orgs_for_user(session, user_email=user_email)
    if existing:
        member = repo.get_membership(session, org_id=existing[0].id, user_email=user_email)
        assert member is not None
        return member
    role = UserRole.OWNER if user_email.lower() in _admin_emails() else UserRole.VIEWER
    member = repo.create_membership(
        session, org_id=DEFAULT_ORG_ID, user_email=user_email, role=role
    )
    session.commit()
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
    email) pair is a no-op regardless of the role param."""
    existing = repo.get_membership(session, org_id=org_id, user_email=user_email)
    if existing is not None:
        return existing
    role = role_override or (
        UserRole.OWNER if user_email.lower() in _admin_emails() else UserRole.VIEWER
    )
    member = repo.create_membership(session, org_id=org_id, user_email=user_email, role=role)
    session.commit()
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
]
