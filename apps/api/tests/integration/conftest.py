import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.postgres import PostgresContainer

# Auth env vars are read lazily (per-request, not at import time) by api.auth /
# api.routers.auth, but must exist before the first request any test makes.
os.environ.setdefault("SESSION_JWT_SECRET", "test-session-secret-at-least-32-bytes-long")
os.environ.setdefault("AGENT_FACTORY_SERVICE_TOKEN", "test-service-token")
os.environ.setdefault("AUTH_DEV_MODE", "true")

from api.db.session import get_db, make_session_factory  # noqa: E402
from api.main import app  # noqa: E402

API_DIR = Path(__file__).resolve().parents[2]


def _run_migrations(database_url: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
        check=True,
    )


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:16", driver="psycopg") as postgres:
        url = postgres.get_connection_url()
        _run_migrations(url)
        yield url


@pytest.fixture(scope="session")
def session_factory(postgres_url: str) -> sessionmaker[Session]:
    return make_session_factory(postgres_url)


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        session.execute(
            text(
                "TRUNCATE tickets, ticket_events, approvals, users "
                "RESTART IDENTITY CASCADE"
            )
        )
        session.execute(text("ALTER SEQUENCE ticket_seq RESTART WITH 1"))
        session.commit()
        yield session
        session.rollback()


@pytest.fixture
def client(db_session: Session, session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    # Default to the trusted service principal so existing tests, which don't care about
    # auth specifics, keep exercising their actual behavior; auth-specific tests override
    # this header per-request (see test_auth_api.py).
    headers = {"Authorization": f"Bearer {os.environ['AGENT_FACTORY_SERVICE_TOKEN']}"}
    with TestClient(app, headers=headers) as test_client:
        yield test_client
    app.dependency_overrides.clear()
