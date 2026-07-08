import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.postgres import PostgresContainer

# Auth env vars are read lazily (per-request, not at import time) by api.auth /
# api.routers.auth, but must exist before the first request any test makes.
os.environ.setdefault("SESSION_JWT_SECRET", "test-session-secret-at-least-32-bytes-long")
os.environ.setdefault("AGENT_FACTORY_SERVICE_TOKEN", "test-service-token")
os.environ.setdefault("AUTH_DEV_MODE", "true")
# T-202: platform-fallback key for orgs with no configured BYOK ProviderKey rows
# (provider_key_service.resolve_runtime_credentials) — never used to make a real call
# in tests (route()/llm_router calls are monkeypatched/faked throughout), only needs
# to be a non-empty string so the dispatch gate doesn't refuse for lack of *a* key.
os.environ.setdefault("VAULT_ADDR", "http://localhost:8200")
os.environ.setdefault("VAULT_TOKEN", "test-vault-token")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-fake-key-not-real")

from api.db.session import get_db, make_session_factory  # noqa: E402
from api.main import app  # noqa: E402
from api.tenancy import DEFAULT_ORG_ID  # noqa: E402
from api.vault_client import VaultClient  # noqa: E402

API_DIR = Path(__file__).resolve().parents[2]
VAULT_TEST_TOKEN = "test-vault-token"


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


@pytest.fixture(scope="session")
def vault_addr() -> Iterator[str]:
    """T-202: a real, throwaway Vault dev-mode container — same pattern as
    postgres_url above. Only tests that request this fixture pay the container-start
    cost; the module-level VAULT_ADDR default (localhost:8200, likely nothing
    listening) is fine for every other test, since they never hit a real key."""
    container = (
        DockerContainer("hashicorp/vault:1.17")
        .with_env("VAULT_DEV_ROOT_TOKEN_ID", VAULT_TEST_TOKEN)
        .with_env("VAULT_DEV_LISTEN_ADDRESS", "0.0.0.0:8200")
        .with_exposed_ports(8200)
    )
    with container:
        wait_for_logs(container, r"Vault server started!", timeout=30)
        addr = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(8200)}"
        old_addr = os.environ.get("VAULT_ADDR")
        old_token = os.environ.get("VAULT_TOKEN")
        os.environ["VAULT_ADDR"] = addr
        os.environ["VAULT_TOKEN"] = VAULT_TEST_TOKEN
        try:
            yield addr
        finally:
            if old_addr is not None:
                os.environ["VAULT_ADDR"] = old_addr
            if old_token is not None:
                os.environ["VAULT_TOKEN"] = old_token


@pytest.fixture
def vault_client(vault_addr: str) -> VaultClient:
    return VaultClient(addr=vault_addr, token=VAULT_TEST_TOKEN)


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        session.execute(
            text(
                "TRUNCATE tickets, ticket_events, approvals, users, orgs "
                "RESTART IDENTITY CASCADE"
            )
        )
        session.execute(text("ALTER SEQUENCE ticket_seq RESTART WITH 1"))
        session.execute(
            text(
                "INSERT INTO orgs (id, name, created_at) VALUES "
                f"('{DEFAULT_ORG_ID}', 'Default Org', now())"
            )
        )
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
