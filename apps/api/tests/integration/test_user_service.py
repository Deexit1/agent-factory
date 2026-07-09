import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.db.models import UserRole
from api.repositories import org_repository
from api.repositories import user_repository as repo
from api.services import org_service, user_service
from api.tenancy import DEFAULT_ORG_ID


def test_get_or_create_user_creates_a_plain_user_row(db_session: Session) -> None:
    user = user_service.get_or_create_user(db_session, "new-user@example.com")

    assert user.email == "new-user@example.com"
    assert user.is_platform_staff is False


def test_get_or_create_user_is_idempotent(db_session: Session) -> None:
    first = user_service.get_or_create_user(db_session, "again@example.com")
    second = user_service.get_or_create_user(db_session, "again@example.com")

    assert first.email == second.email


def test_duplicate_email_insert_raises_integrity_error(db_session: Session) -> None:
    """Regression guard for the fix in get_or_create_user: two concurrent first-logins for
    the same email both pass the get_user() check before either commits, so the loser's
    INSERT must fail with IntegrityError specifically (not some other exception type) for
    the service's except-and-refetch recovery to catch it."""
    repo.create_user(db_session, "race@example.com")
    db_session.commit()

    with pytest.raises(IntegrityError):
        repo.create_user(db_session, "race@example.com")
    db_session.rollback()


def test_duplicate_membership_insert_raises_integrity_error(db_session: Session) -> None:
    """T-206 regression guard: the same race as get_or_create_user's, one level up —
    two concurrent dev-logins (or two parallel Playwright workers hitting the same
    fixed test email, the actual real-world trigger this fix was written for) for the
    same (org_id, email) pair both pass get_or_create_dev_membership's/
    ensure_default_org_membership's "no existing membership" check before either
    commits, so the loser's INSERT must fail with IntegrityError specifically for
    org_service's except-and-refetch recovery to catch it."""
    user_service.get_or_create_user(db_session, "race-member@example.com")
    org_repository.create_membership(
        db_session,
        org_id=DEFAULT_ORG_ID,
        user_email="race-member@example.com",
        role=UserRole.VIEWER,
    )
    db_session.commit()

    with pytest.raises(IntegrityError):
        org_repository.create_membership(
            db_session,
            org_id=DEFAULT_ORG_ID,
            user_email="race-member@example.com",
            role=UserRole.VIEWER,
        )
    db_session.rollback()


def test_get_or_create_dev_membership_is_idempotent(db_session: Session) -> None:
    """T-201: role now lives on org_members, not User — first login's role wins;
    a later dev-login for the same (org, email) pair is a no-op."""
    user_service.get_or_create_user(db_session, "member@example.com")

    first = org_service.get_or_create_dev_membership(
        db_session,
        org_id=DEFAULT_ORG_ID,
        user_email="member@example.com",
        role_override=UserRole.OWNER,
    )
    second = org_service.get_or_create_dev_membership(
        db_session,
        org_id=DEFAULT_ORG_ID,
        user_email="member@example.com",
        role_override=UserRole.VIEWER,
    )

    assert first.id == second.id
    assert second.role == UserRole.OWNER
