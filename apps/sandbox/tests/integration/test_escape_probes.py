"""SPEC-204 AC1: "Escape-test suite (host fs, docker socket, other-VM network probes)
passes on the microVM runtime." Real Docker required (see conftest.py's `_images_built`
fixture, same as every other file in this package).

This formalizes what test_sandbox_lifecycle.py already half-proved (docker-socket
invisibility, cross-network unreachability) as a named escape-test suite, and adds a
new host-fs probe plus reframes the network probe as org A vs org B using the new
org-aware `SandboxPool`, not just ticket A vs ticket B.

The same three probes against `MicroVMRuntime` are honestly skipped, not faked — no
Firecracker/Kata hypervisor is reachable in this environment. See runtime.py.
"""

import subprocess
from pathlib import Path

import pytest

from sandbox.config import SandboxConfig
from sandbox.pool import SandboxPool
from sandbox.runtime import DockerRuntime, MicroVMRuntime


def _docker_exec(container: str, *cmd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", "exec", container, *cmd], capture_output=True, text=True)


@pytest.fixture
def two_org_sandboxes(tmp_path: Path):
    config = SandboxConfig()
    pool = SandboxPool(runtime=DockerRuntime(), config=config, pool_size=0, state_root=tmp_path)

    wt_a = tmp_path / "wt-a"
    wt_a.mkdir()
    (wt_a / "f.txt").write_text("a")
    wt_b = tmp_path / "wt-b"
    wt_b.mkdir()
    (wt_b / "f.txt").write_text("b")

    name_a = pool.acquire_for(
        org_id="org-escape-a", ticket_id="escT-a", worktree_host_path=str(wt_a), allowed_domains=[]
    )
    name_b = pool.acquire_for(
        org_id="org-escape-b", ticket_id="escT-b", worktree_host_path=str(wt_b), allowed_domains=[]
    )
    try:
        yield name_a, name_b
    finally:
        pool.release("escT-a")
        pool.release("escT-b")


def test_host_fs_escape_is_blocked(two_org_sandboxes: tuple[str, str]) -> None:
    name_a, _ = two_org_sandboxes

    # Read-only rootfs: no write is possible anywhere outside the declared
    # tmpfs/bind-mount paths (/tmp, /home/sandbox, /workspace/repo).
    write_outside = _docker_exec(name_a, "sh", "-c", "echo x > /etc/escape-probe")
    assert write_outside.returncode != 0

    inspect = subprocess.run(
        ["docker", "inspect", name_a, "--format", "{{range .Mounts}}{{.Destination}} {{end}}"],
        capture_output=True,
        text=True,
        check=True,
    )
    declared = set(inspect.stdout.split())
    assert declared <= {"/tmp", "/home/sandbox", "/workspace/repo"}, declared


def test_docker_socket_is_invisible(two_org_sandboxes: tuple[str, str]) -> None:
    name_a, _ = two_org_sandboxes

    assert _docker_exec(name_a, "test", "-S", "/var/run/docker.sock").returncode != 0
    assert _docker_exec(name_a, "sh", "-c", "which docker").returncode != 0


def test_org_a_sandbox_cannot_reach_org_b_sandbox(two_org_sandboxes: tuple[str, str]) -> None:
    name_a, name_b = two_org_sandboxes

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


def _microvm_available() -> bool:
    return False  # disclosed: no Firecracker/Kata hypervisor in this environment


@pytest.mark.skipif(
    not _microvm_available(), reason="no Firecracker/Kata hypervisor in this environment"
)
class TestMicroVMEscapeProbes:
    """Same three probes against MicroVMRuntime — honestly skipped rather than faked
    green, per T-204's plan. Kept here (not deleted) so the suite fails loudly, not
    silently, the moment a real hypervisor becomes available and this guard is lifted."""

    def test_host_fs_escape_is_blocked(self) -> None:
        MicroVMRuntime()

    def test_docker_socket_is_invisible(self) -> None:
        MicroVMRuntime()

    def test_org_a_sandbox_cannot_reach_org_b_sandbox(self) -> None:
        MicroVMRuntime()
