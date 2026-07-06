import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.db.models import UserRole
from api.repositories import user_repository as repo
from api.services import user_service
from api.tenancy import DEFAULT_ORG_ID


def test_get_or_create_user_creates_viewer_by_default(db_session: Session) -> None:
    user = user_service.get_or_create_user(db_session, "new-user@example.com")

    assert user.role == UserRole.VIEWER


def test_get_or_create_user_is_idempotent(db_session: Session) -> None:
    first = user_service.get_or_create_user(
        db_session, "again@example.com", role_override=UserRole.ADMIN
    )
    second = user_service.get_or_create_user(
        db_session, "again@example.com", role_override=UserRole.VIEWER
    )

    assert first.email == second.email
    assert second.role == UserRole.ADMIN  # first login's role wins; second call is a no-op


def test_duplicate_email_insert_raises_integrity_error(db_session: Session) -> None:
    """Regression guard for the fix in get_or_create_user: two concurrent first-logins for
    the same email both pass the get_user() check before either commits, so the loser's
    INSERT must fail with IntegrityError specifically (not some other exception type) for
    the service's except-and-refetch recovery to catch it."""
    repo.create_user(db_session, "race@example.com", UserRole.VIEWER, org_id=DEFAULT_ORG_ID)
    db_session.commit()

    with pytest.raises(IntegrityError):
        repo.create_user(db_session, "race@example.com", UserRole.VIEWER, org_id=DEFAULT_ORG_ID)
    db_session.rollback()
