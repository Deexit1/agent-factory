import os
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
API_DIR = REPO_ROOT / "apps" / "api"
SANDBOX_DIR = REPO_ROOT / "apps" / "sandbox"

TEST_POSTGRES_PORT = 55499
TEST_API_PORT = 18099
SERVICE_TOKEN = "sandbox-test-service-token-at-least-32-bytes"


def _api_python() -> str:
    for candidate in ("bin/python", "Scripts/python.exe", "Scripts/python"):
        path = API_DIR / ".venv" / candidate
        if path.exists():
            return str(path)
    raise RuntimeError(f"no venv python found under {API_DIR / '.venv'}")


@pytest.fixture(scope="session", autouse=True)
def _images_built() -> None:
    """Build/pull the images every test in this suite depends on, once per run."""
    subprocess.run(
        [
            "docker",
            "build",
            "-t",
            "agent-factory-sandbox:latest",
            "-f",
            str(SANDBOX_DIR / "images" / "Dockerfile"),
            str(SANDBOX_DIR / "images"),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(["docker", "pull", "ubuntu/squid:latest"], check=True, capture_output=True)


@pytest.fixture
def ticket_id() -> str:
    return f"testT{uuid.uuid4().hex[:8]}"


@pytest.fixture
def origin_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "origin"
    repo.mkdir()

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    (repo / "README.md").write_text("hello\n")
    git("add", "README.md")
    git("commit", "-q", "-m", "initial commit")
    return repo


@pytest.fixture(scope="session")
def running_api() -> Iterator[str]:
    """A real, migrated apps/api instance backed by a real (throwaway) Postgres.

    Used only by the AC5 egress-logging test — every other sandbox test is
    independent of the ticket API.
    """
    container = f"sandbox-test-postgres-{uuid.uuid4().hex[:8]}"
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
        # Also set on this process's own environ, not just the api subprocess's: the
        # sandbox egress forwarder this test suite spawns (see cli.up) is itself a
        # subprocess of THIS process and inherits os.environ, not the dict below.
        os.environ["AGENT_FACTORY_SERVICE_TOKEN"] = SERVICE_TOKEN
        env = {
            **os.environ,
            "DATABASE_URL": database_url,
            "AGENT_FACTORY_SERVICE_TOKEN": SERVICE_TOKEN,
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
