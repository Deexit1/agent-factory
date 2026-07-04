from datetime import UTC, datetime

from sqlalchemy.orm import Session

from api.db.models import User, UserRole


def get_user(session: Session, email: str) -> User | None:
    return session.get(User, email)


def create_user(session: Session, email: str, role: UserRole) -> User:
    user = User(email=email, role=role, created_at=datetime.now(UTC))
    session.add(user)
    session.flush()
    return user
