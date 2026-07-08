import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.models import Org, OrgInvite, OrgInviteStatus, OrgMember, StaffAuditLog, UserRole


def create_org(session: Session, *, name: str) -> Org:
    org = Org(id=f"org-{secrets.token_urlsafe(8)}", name=name, created_at=datetime.now(UTC))
    session.add(org)
    session.flush()
    return org


def get_org(session: Session, org_id: str) -> Org | None:
    return session.get(Org, org_id)


def get_membership(session: Session, *, org_id: str, user_email: str) -> OrgMember | None:
    return session.execute(
        select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_email == user_email)
    ).scalar_one_or_none()


def create_membership(
    session: Session, *, org_id: str, user_email: str, role: UserRole
) -> OrgMember:
    member = OrgMember(
        org_id=org_id, user_email=user_email, role=role, created_at=datetime.now(UTC)
    )
    session.add(member)
    session.flush()
    return member


def list_members(session: Session, *, org_id: str) -> list[OrgMember]:
    return list(
        session.execute(
            select(OrgMember).where(OrgMember.org_id == org_id).order_by(OrgMember.id)
        )
        .scalars()
        .all()
    )


def list_orgs_for_user(session: Session, *, user_email: str) -> list[Org]:
    return list(
        session.execute(
            select(Org)
            .join(OrgMember, OrgMember.org_id == Org.id)
            .where(OrgMember.user_email == user_email)
            .order_by(OrgMember.id)
        )
        .scalars()
        .all()
    )


def create_invite(
    session: Session, *, org_id: str, email: str, role: UserRole, invited_by: str
) -> OrgInvite:
    invite = OrgInvite(
        org_id=org_id,
        email=email,
        role=role,
        invited_by=invited_by,
        token=secrets.token_urlsafe(24),
        status=OrgInviteStatus.PENDING,
        created_at=datetime.now(UTC),
    )
    session.add(invite)
    session.flush()
    return invite


def get_invite_by_token(session: Session, token: str) -> OrgInvite | None:
    return session.execute(
        select(OrgInvite).where(OrgInvite.token == token)
    ).scalar_one_or_none()


def accept_invite(session: Session, invite: OrgInvite) -> OrgMember:
    member = create_membership(
        session, org_id=invite.org_id, user_email=invite.email, role=invite.role
    )
    invite.status = OrgInviteStatus.ACCEPTED
    invite.accepted_at = datetime.now(UTC)
    session.flush()
    return member


def record_staff_audit(
    session: Session, *, staff_email: str, org_id: str, action: str, path: str | None = None
) -> StaffAuditLog:
    entry = StaffAuditLog(
        staff_email=staff_email, org_id=org_id, action=action, path=path, ts=datetime.now(UTC)
    )
    session.add(entry)
    session.flush()
    return entry
