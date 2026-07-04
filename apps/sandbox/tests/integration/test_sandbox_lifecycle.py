import json
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from sandbox import cli, docker_runtime
from sandbox.config import SandboxConfig

from .conftest import SERVICE_TOKEN

_AUTH_HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}


def _docker_exec(container: str, *cmd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", "exec", container, *cmd], capture_output=True, text=True)


@pytest.fixture
def sandbox(ticket_id: str, origin_repo: Path):
    config = SandboxConfig(api_url="http://127.0.0.1:1")  # unreachable; AC1-4 don't need the API
    cli.up(ticket_id, str(origin_repo), "main", config)
    try:
        yield ticket_id
    finally:
        cli.down(ticket_id)


def test_up_starts_sandbox_and_proxy_containers(sandbox: str) -> None:
    assert docker_runtime.container_exists(docker_runtime.sandbox_name(sandbox))
    assert docker_runtime.container_exists(docker_runtime.proxy_name(sandbox))


def test_blocked_domain_fails_and_allowed_domain_succeeds(sandbox: str) -> None:
    name = docker_runtime.sandbox_name(sandbox)

    blocked = _docker_exec(
        name,
        "curl",
        "-s",
        "-o",
        "/dev/null",
        "-w",
        "%{http_code}",
        "--max-time",
        "5",
        "https://blocked.example.com",
    )
    assert blocked.stdout.strip() != "200"

    allowed = _docker_exec(name, "pip", "install", "--quiet", "requests")
    assert allowed.returncode == 0, allowed.stderr


def test_push_to_main_rejected_push_to_agent_branch_succeeds(sandbox: str) -> None:
    name = docker_runtime.sandbox_name(sandbox)
    _docker_exec(name, "sh", "-c", "cd /workspace/repo && git config user.email t@e.com")
    _docker_exec(name, "sh", "-c", "cd /workspace/repo && git config user.name Test")
    _docker_exec(
        name,
        "sh",
        "-c",
        "cd /workspace/repo && echo change >> README.md && git add -A && git commit -q -m x",
    )

    rejected = _docker_exec(name, "sh", "-c", "cd /workspace/repo && git push origin HEAD:main")
    assert rejected.returncode != 0
    assert "rejected" in rejected.stderr

    allowed = _docker_exec(
        name, "sh", "-c", f"cd /workspace/repo && git push origin agent/{sandbox}"
    )
    assert allowed.returncode == 0, allowed.stderr


def test_sandbox_cannot_see_docker_socket(sandbox: str) -> None:
    name = docker_runtime.sandbox_name(sandbox)

    assert _docker_exec(name, "test", "-S", "/var/run/docker.sock").returncode != 0
    assert _docker_exec(name, "sh", "-c", "which docker").returncode != 0


def test_two_sandboxes_cannot_reach_each_other(
    ticket_id: str, origin_repo: Path, tmp_path: Path
) -> None:
    other_ticket_id = f"{ticket_id}-other"
    other_repo = tmp_path / "origin-other"
    other_repo.mkdir()
    for args in (
        ["init", "-q", "-b", "main"],
        ["config", "user.email", "t@e.com"],
        ["config", "user.name", "Test"],
    ):
        subprocess.run(["git", "-C", str(other_repo), *args], check=True, capture_output=True)
    (other_repo / "f.txt").write_text("x")
    subprocess.run(["git", "-C", str(other_repo), "add", "f.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(other_repo), "commit", "-q", "-m", "init"],
        check=True,
        capture_output=True,
    )

    config = SandboxConfig(api_url="http://127.0.0.1:1")
    cli.up(ticket_id, str(origin_repo), "main", config)
    cli.up(other_ticket_id, str(other_repo), "main", config)
    try:
        name_a = docker_runtime.sandbox_name(ticket_id)
        name_b = docker_runtime.sandbox_name(other_ticket_id)

        resolve = _docker_exec(name_a, "getent", "hosts", name_b)
        assert resolve.returncode != 0

        inspect = subprocess.run(
            [
                "docker",
                "inspect",
                name_b,
                "--format",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        other_ip = inspect.stdout.strip()
        unreachable = _docker_exec(name_a, "curl", "-s", "-m", "3", f"http://{other_ip}:3128/")
        assert unreachable.returncode != 0
    finally:
        cli.down(ticket_id)
        cli.down(other_ticket_id)


def test_down_leaves_no_container_network_or_credential(ticket_id: str, origin_repo: Path) -> None:
    config = SandboxConfig(api_url="http://127.0.0.1:1")
    cli.up(ticket_id, str(origin_repo), "main", config)

    cli.down(ticket_id)

    assert not docker_runtime.container_exists(docker_runtime.sandbox_name(ticket_id))
    assert not docker_runtime.container_exists(docker_runtime.proxy_name(ticket_id))
    assert not docker_runtime.network_exists(docker_runtime.network_name(ticket_id))

    from sandbox import credential_broker

    assert credential_broker.get(ticket_id) is None

    worktree_path = cli.state_dir_for(ticket_id) / "worktree"
    assert not worktree_path.exists()


def test_egress_attempts_are_logged_as_ticket_events(
    ticket_id: str, origin_repo: Path, running_api: str
) -> None:
    create_req = urllib.request.Request(
        f"{running_api}/tickets",
        method="POST",
        headers={"Content-Type": "application/json", **_AUTH_HEADERS},
        data=b'{"type":"task","title":"sandbox test","created_by":"human:test",'
        b'"budget_usd":10,"acceptance_criteria":[{"id":"AC-1","description":"d","verification":"v"}]}',
    )
    with urllib.request.urlopen(create_req) as response:
        real_ticket_id = json.loads(response.read())["id"]

    config = SandboxConfig(api_url=running_api)
    cli.up(real_ticket_id, str(origin_repo), "main", config)
    try:
        name = docker_runtime.sandbox_name(real_ticket_id)
        _docker_exec(name, "curl", "-s", "-o", "/dev/null", "--max-time", "5", "https://pypi.org/")
        _docker_exec(
            name, "curl", "-s", "-o", "/dev/null", "--max-time", "5", "https://blocked.example.com"
        )

        # Forwarding is async (curl -> squid access log -> tail -F -> HTTP POST), and CI
        # runners are slower/noisier than a local box, so poll instead of a fixed sleep.
        egress_events: list[dict[str, object]] = []
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            events_req = urllib.request.Request(
                f"{running_api}/tickets/{real_ticket_id}/events", headers=_AUTH_HEADERS
            )
            with urllib.request.urlopen(events_req) as response:
                events = json.loads(response.read())["items"]
            egress_events = [e for e in events if e["kind"] == "tool_call"]
            domains_seen = {e["payload"]["egress"] for e in egress_events}
            if {"pypi.org", "blocked.example.com"} <= domains_seen:
                break
            time.sleep(1)

        assert any(
            e["payload"]["egress"] == "pypi.org" and e["payload"]["allowed"] for e in egress_events
        ), egress_events
        assert any(
            e["payload"]["egress"] == "blocked.example.com" and not e["payload"]["allowed"]
            for e in egress_events
        ), egress_events
    finally:
        cli.down(real_ticket_id)
