from datetime import UTC, datetime

from sqlalchemy.orm import Session

from api.db.models import User, UserRole


def get_user(session: Session, email: str, *, org_id: str) -> User | None:
    user = session.get(User, email)
    if user is None or user.org_id != org_id:
        return None
    return user


def create_user(session: Session, email: str, role: UserRole, *, org_id: str) -> User:
    user = User(email=email, org_id=org_id, role=role, created_at=datetime.now(UTC))
    session.add(user)
    session.flush()
    return user
