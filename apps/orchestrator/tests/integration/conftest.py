import os
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from orchestrator.api_client import ApiClient
from orchestrator.config import DevAgentConfig

REPO_ROOT = Path(__file__).resolve().parents[4]
API_DIR = REPO_ROOT / "apps" / "api"
FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"

TEST_POSTGRES_PORT = 55599
TEST_API_PORT = 18199
SERVICE_TOKEN = "orchestrator-test-service-token-at-least-32-bytes"


def _api_python() -> str:
    for candidate in ("bin/python", "Scripts/python.exe", "Scripts/python"):
        path = API_DIR / ".venv" / candidate
        if path.exists():
            return str(path)
    raise RuntimeError(f"no venv python found under {API_DIR / '.venv'}")


@pytest.fixture(scope="session")
def running_api() -> Iterator[str]:
    """A real, migrated apps/api instance backed by a real (throwaway) Postgres —
    needed for AC #5 (cost_ledger sum must match agent_runs, verified against real DB
    arithmetic, not mocked)."""
    container = f"orchestrator-test-postgres-{uuid.uuid4().hex[:8]}"
    database_url = (
        f"postgresql+psycopg://agent_factory:change-me@localhost:{TEST_POSTGRES_PORT}/agent_factory"
    )
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container,
            "-p",
            f"{TEST_POSTGRES_PORT}:5432",
            "-e",
            "POSTGRES_USER=agent_factory",
            "-e",
            "POSTGRES_PASSWORD=change-me",
            "-e",
            "POSTGRES_DB=agent_factory",
            "postgres:16",
        ],
        check=True,
        capture_output=True,
    )
    try:
        python = _api_python()
        env = {
            **os.environ,
            "DATABASE_URL": database_url,
            "AGENT_FACTORY_SERVICE_TOKEN": SERVICE_TOKEN,
            "AUTH_DEV_MODE": "true",
            "SESSION_JWT_SECRET": "test-session-secret-at-least-32-bytes-long",
        }
        _wait_for_postgres(python, database_url)

        subprocess.run(
            [python, "-m", "alembic", "upgrade", "head"],
            cwd=API_DIR,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

        api_process = subprocess.Popen(
            [
                python,
                "-m",
                "uvicorn",
                "api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(TEST_API_PORT),
            ],
            cwd=API_DIR,
            env=env,
        )
        api_url = f"http://127.0.0.1:{TEST_API_PORT}"
        try:
            _wait_for_http(f"{api_url}/health")
            yield api_url
        finally:
            api_process.terminate()
            api_process.wait(timeout=10)
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)


def _wait_for_postgres(python: str, database_url: str, attempts: int = 30) -> None:
    plain_url = database_url.replace("+psycopg", "")
    for _ in range(attempts):
        result = subprocess.run(
            [python, "-c", f"import psycopg; psycopg.connect('{plain_url}')"],
            capture_output=True,
        )
        if result.returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError("postgres did not become ready in time")


def _wait_for_http(url: str, attempts: int = 30) -> None:
    import urllib.request

    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=1) as response:  # noqa: S310
                if response.status == 200:
                    return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"{url} did not become ready in time")


@pytest.fixture
def api(running_api: str) -> ApiClient:
    return ApiClient(running_api, service_token=SERVICE_TOKEN)


@pytest.fixture
def config(running_api: str) -> DevAgentConfig:
    return DevAgentConfig(api_url=running_api, timeout_s=5.0)


@pytest.fixture
def create_ticket(running_api: str):
    def _create(budget_usd: float = 5.0) -> dict[str, object]:
        import json
        import urllib.request

        request = urllib.request.Request(
            f"{running_api}/tickets",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {SERVICE_TOKEN}",
            },
            data=json.dumps(
                {
                    "type": "task",
                    "title": "Add /health endpoint",
                    "created_by": "human:test",
                    "budget_usd": budget_usd,
                    "acceptance_criteria": [
                        {
                            "id": "AC-1",
                            "description": "GET /health returns 200",
                            "verification": "test_app.py::test_health_returns_200",
                        }
                    ],
                }
            ).encode(),
        )
        with urllib.request.urlopen(request) as response:
            result: dict[str, object] = json.loads(response.read())
            return result

    return _create


@pytest.fixture
def transition(running_api: str):
    def _transition(ticket_id: str, to_state: str, actor: str = "human:test") -> None:
        import json
        import urllib.request

        request = urllib.request.Request(
            f"{running_api}/tickets/{ticket_id}/transition",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {SERVICE_TOKEN}",
            },
            data=json.dumps({"to_state": to_state, "actor": actor}).encode(),
        )
        urllib.request.urlopen(request)

    return _transition


@pytest.fixture
def toy_repo(tmp_path: Path) -> Path:
    """A minimal git repo the dev agent 'edits' — plain app.py with no /health route.

    Has a real "origin" remote (a bare repo) so git_ops.push has somewhere to push
    to — production points this at the real git host instead.
    """
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)

    repo = tmp_path / "toy-repo"
    repo.mkdir()

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    git("remote", "add", "origin", str(origin))
    (repo / "app.py").write_text("def create_app():\n    routes = {}\n    return routes\n")
    git("add", "app.py")
    git("commit", "-q", "-m", "initial commit")
    git("push", "-q", "origin", "main")
    return repo


@pytest.fixture
def fixture_dir() -> Path:
    return FIXTURES_DIR / "add_health_endpoint"
