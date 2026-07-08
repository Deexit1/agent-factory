from datetime import UTC, datetime

from sqlalchemy.orm import Session

from api.db.models import User


def get_user(session: Session, email: str) -> User | None:
    return session.get(User, email)


def create_user(session: Session, email: str, *, is_platform_staff: bool = False) -> User:
    user = User(email=email, is_platform_staff=is_platform_staff, created_at=datetime.now(UTC))
    session.add(user)
    session.flush()
    return user
