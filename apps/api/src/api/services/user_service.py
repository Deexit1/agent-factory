import os

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.db.models import User
from api.repositories import user_repository as repo


def _staff_emails() -> set[str]:
    raw = os.environ.get("PLATFORM_STAFF_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def get_or_create_user(session: Session, email: str) -> User:
    """First login for an email creates its `users` row (SPEC-006). T-201: no longer
    touches org membership at all — that's a separate concern
    (org_service.ensure_default_org_membership / get_or_create_dev_membership),
    since a user's role is per-org now, not global.

    Two concurrent first-logins for the same email (e.g. two tabs) can both pass the
    initial get_user() check before either commits; the loser's INSERT hits the unique
    constraint on email, so we catch that and re-fetch the winner's row instead of 500ing.
    """
    user = repo.get_user(session, email)
    if user is not None:
        return user

    is_staff = email.lower() in _staff_emails()
    try:
        user = repo.create_user(session, email, is_platform_staff=is_staff)
        session.commit()
    except IntegrityError:
        session.rollback()
        user = repo.get_user(session, email)
        assert user is not None  # the constraint that just failed guarantees this row exists
    return user


__all__ = ["get_or_create_user"]
