import os

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.db.models import User, UserRole
from api.repositories import user_repository as repo
from api.tenancy import DEFAULT_ORG_ID


def _admin_emails() -> set[str]:
    return {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}


def get_or_create_user(
    session: Session,
    email: str,
    *,
    role_override: UserRole | None = None,
    org_id: str = DEFAULT_ORG_ID,
) -> User:
    """First login for an email creates its `users` row (SPEC-006).

    Defaults to viewer unless the email is pre-seeded via ADMIN_EMAILS (pilot bootstrap) or
    a role_override is given (dev-login only — never trusted from a real OIDC callback).
    org_id defaults to the single seeded org (T-102 groundwork); real per-user org
    resolution (invites, membership across multiple orgs) is T-201.

    Two concurrent first-logins for the same email (e.g. two tabs) can both pass the
    initial get_user() check before either commits; the loser's INSERT hits the unique
    constraint on email, so we catch that and re-fetch the winner's row instead of 500ing.
    """
    user = repo.get_user(session, email, org_id=org_id)
    if user is not None:
        return user

    is_admin_email = email.lower() in _admin_emails()
    role = role_override or (UserRole.ADMIN if is_admin_email else UserRole.VIEWER)
    try:
        user = repo.create_user(session, email, role, org_id=org_id)
        session.commit()
    except IntegrityError:
        session.rollback()
        user = repo.get_user(session, email, org_id=org_id)
        assert user is not None  # the constraint that just failed guarantees this row exists
    return user


__all__ = ["get_or_create_user"]
