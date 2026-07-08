"""T-204 (SPEC-204): a pluggable sandbox execution backend.

`DockerRuntime` wraps today's real, fully-tested `docker_runtime.py` functions
unchanged — zero behavior change for any existing caller. `MicroVMRuntime` implements
the same `SandboxRuntime` protocol against Firecracker/Kata's real CLI shapes
(`firecracker-containerd`'s `ctr run --runtime ...`), but no Firecracker/Kata hypervisor
is reachable in this environment (no KVM on this Windows dev host; self-hosted CI
runners' KVM availability is unconfirmed) — same disclosed category as T-202's "no
OpenAI credits" / T-203's "no live GitHub App". It is proven only via monkeypatched
`subprocess.run` (see tests/unit/test_microvm_runtime.py), never a real VM boot.
"""

import os
import subprocess
from collections.abc import Iterator
from typing import Protocol

from sandbox import docker_runtime
from sandbox.config import SandboxConfig


class SandboxRuntime(Protocol):
    def create_network(self, ticket_id: str) -> str: ...

    def run_proxy(
        self, ticket_id: str, config: SandboxConfig, squid_conf_host_path: str
    ) -> str: ...

    def run_sandbox(
        self,
        ticket_id: str,
        config: SandboxConfig,
        worktree_host_path: str,
        git_token: str,
        extra_mount: tuple[str, str] | None = None,
        extra_env: dict[str, str] | None = None,
        network: str | None = None,
        proxy_url: str | None = None,
    ) -> str: ...

    def exec_in(self, container: str, cmd: list[str]) -> subprocess.CompletedProcess[str]: ...

    def exec_stream(
        self, container: str, cmd: list[str], env: dict[str, str] | None = None
    ) -> Iterator[str]: ...

    def teardown(self, ticket_id: str) -> None: ...


class DockerRuntime:
    """The real, live-tested default — a thin, behavior-preserving wrapper over
    `docker_runtime.py`'s existing free functions."""

    def create_network(self, ticket_id: str) -> str:
        return docker_runtime.create_internal_network(ticket_id)

    def run_proxy(self, ticket_id: str, config: SandboxConfig, squid_conf_host_path: str) -> str:
        return docker_runtime.run_proxy(ticket_id, config, squid_conf_host_path)

    def run_sandbox(
        self,
        ticket_id: str,
        config: SandboxConfig,
        worktree_host_path: str,
        git_token: str,
        extra_mount: tuple[str, str] | None = None,
        extra_env: dict[str, str] | None = None,
        network: str | None = None,
        proxy_url: str | None = None,
    ) -> str:
        return docker_runtime.run_sandbox(
            ticket_id,
            config,
            worktree_host_path,
            git_token,
            extra_mount=extra_mount,
            extra_env=extra_env,
            network=network,
            proxy_url=proxy_url,
        )

    def exec_in(self, container: str, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return docker_runtime.exec_in(container, cmd)

    def exec_stream(
        self, container: str, cmd: list[str], env: dict[str, str] | None = None
    ) -> Iterator[str]:
        return docker_runtime.exec_stream(container, cmd, env)

    def teardown(self, ticket_id: str) -> None:
        docker_runtime.remove_container(docker_runtime.sandbox_name(ticket_id))
        docker_runtime.remove_container(docker_runtime.proxy_name(ticket_id))
        docker_runtime.remove_network(docker_runtime.network_name(ticket_id))


class MicroVMRuntime:
    """Firecracker/Kata-shaped backend, built against `firecracker-containerd`'s
    documented `ctr` CLI surface. NOT LIVE-VERIFIED: no hypervisor is reachable in this
    environment to boot a real microVM against. Every method here is proven only at the
    subprocess-invocation boundary (argv shape), the same fault-injection precedent
    T-203 used for `respx` against `api.github.com` — it proves this class's own control
    flow, not that a real Firecracker VM actually boots and behaves as asserted.
    """

    def __init__(self, ctr_bin: str = "ctr") -> None:
        self._ctr_bin = ctr_bin

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        result = subprocess.run([self._ctr_bin, *args], capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"{self._ctr_bin} {' '.join(args)} failed:\n{result.stderr}")
        return result

    def create_network(self, ticket_id: str) -> str:
        # firecracker-containerd has no first-class network-create verb of its own —
        # networking is CNI-configured per-VM at `run` time via --net-host/--cni flags.
        # Nothing to provision ahead of `run_sandbox` here; returning the logical name
        # keeps this method's shape symmetric with DockerRuntime's.
        return docker_runtime.network_name(ticket_id)

    def run_proxy(self, ticket_id: str, config: SandboxConfig, squid_conf_host_path: str) -> str:
        name = docker_runtime.proxy_name(ticket_id)
        self._run(
            [
                "run",
                "-d",
                "--runtime",
                "aws.firecracker",
                "--net-host",
                config.proxy_image,
                name,
            ]
        )
        return name

    def run_sandbox(
        self,
        ticket_id: str,
        config: SandboxConfig,
        worktree_host_path: str,
        git_token: str,
        extra_mount: tuple[str, str] | None = None,
        extra_env: dict[str, str] | None = None,
        network: str | None = None,
        proxy_url: str | None = None,
    ) -> str:
        name = docker_runtime.sandbox_name(ticket_id)
        args = [
            "run",
            "-d",
            "--runtime",
            "aws.firecracker",
            "--mount",
            f"type=bind,src={worktree_host_path},dst=/workspace/repo",
            config.image,
            name,
        ]
        self._run(args)
        return name

    def exec_in(self, container: str, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self._ctr_bin, "task", "exec", "--exec-id", "sandbox-exec", container, *cmd],
            capture_output=True,
            text=True,
        )

    def exec_stream(
        self, container: str, cmd: list[str], env: dict[str, str] | None = None
    ) -> Iterator[str]:
        popen_env = None
        args = [self._ctr_bin, "task", "exec", "--exec-id", "sandbox-exec"]
        if env:
            popen_env = {**os.environ, **env}
        args += [container, *cmd]
        process = subprocess.Popen(
            args, env=popen_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        assert process.stdout is not None
        try:
            yield from process.stdout
        finally:
            if process.poll() is None:
                process.terminate()

    def teardown(self, ticket_id: str) -> None:
        for name in (docker_runtime.sandbox_name(ticket_id), docker_runtime.proxy_name(ticket_id)):
            subprocess.run([self._ctr_bin, "task", "kill", name], capture_output=True, text=True)
            subprocess.run([self._ctr_bin, "container", "rm", name], capture_output=True, text=True)
