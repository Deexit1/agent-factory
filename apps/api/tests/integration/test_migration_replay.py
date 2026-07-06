"""T-102 AC2: "existing Phase-1 tickets replay cleanly through the migrated machine."

Spins up its OWN Postgres container (not the shared session-scoped one from
conftest.py, which is already at head) so it can stop at the pre-T-102 revision,
insert a ticket row exactly as Phase-1 code would have (no org_id column, no
in_review state), then upgrade to head and prove the row survived the org_id
backfill and can still complete its lifecycle through the new state machine.
"""

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from api.db.session import get_db, make_session_factory
from api.main import app

API_DIR = Path(__file__).resolve().parents[2]
PRE_T102_REVISION = "0cf581260d39"


def _alembic(database_url: str, *args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=API_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
        check=True,
    )


@pytest.fixture(scope="module")
def pre_migration_database_url() -> Iterator[str]:
    with PostgresContainer("postgres:16", driver="psycopg") as postgres:
        yield postgres.get_connection_url()


def test_phase1_ticket_survives_migration_and_replays_through_new_machine(
    pre_migration_database_url: str,
) -> None:
    _alembic(pre_migration_database_url, "upgrade", PRE_T102_REVISION)

    session_factory: sessionmaker = make_session_factory(pre_migration_database_url)
    with session_factory() as session:
        # The exact Phase-1 shape (apps/api/src/api/repositories/ticket_repository.py's
        # create_ticket before T-102): no org_id column exists at this revision yet.
        session.execute(
            text(
                """
                INSERT INTO tickets
                    (id, type, state, title, spec, acceptance_criteria, assignee_agent,
                     budget_usd, bounce_count, created_by, created_at)
                VALUES
                    ('T-PHASE1', 'task', 'ready', 'Pre-T-102 ticket', NULL,
                     '[{"id": "AC-1", "description": "d", "verification": "v"}]', NULL,
                     100.0, 0, 'human:alice', now())
                """
            )
        )
        session.commit()

    _alembic(pre_migration_database_url, "upgrade", "head")

    with session_factory() as session:
        org_id = session.execute(
            text("SELECT org_id FROM tickets WHERE id = 'T-PHASE1'")
        ).scalar_one()
        assert org_id == "default"

    def override_get_db() -> Iterator:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    os.environ.setdefault("AGENT_FACTORY_SERVICE_TOKEN", "test-service-token")
    os.environ.setdefault("SESSION_JWT_SECRET", "test-session-secret-at-least-32-bytes-long")
    headers = {"Authorization": f"Bearer {os.environ['AGENT_FACTORY_SERVICE_TOKEN']}"}
    try:
        with TestClient(app, headers=headers) as client:
            get_response = client.get("/tickets/T-PHASE1")
            assert get_response.status_code == 200
            assert get_response.json()["state"] == "ready"

            for to_state in ("in_progress", "in_review", "in_qa", "done"):
                body = {"to_state": to_state, "actor": "human:alice"}
                response = client.post("/tickets/T-PHASE1/transition", json=body)
                assert response.status_code == 200, response.text

            final = client.get("/tickets/T-PHASE1")
            assert final.json()["state"] == "done"
    finally:
        app.dependency_overrides.clear()
