import subprocess
import time
from collections.abc import Iterator

from sandbox.config import SandboxConfig


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)} failed:\n{result.stderr}")
    return result


def _run_ok(args: list[str]) -> bool:
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    return result.returncode == 0


def network_name(ticket_id: str) -> str:
    return f"sandbox-{ticket_id}-internal"


def proxy_name(ticket_id: str) -> str:
    return f"sandbox-{ticket_id}-proxy"


def sandbox_name(ticket_id: str) -> str:
    return f"sandbox-{ticket_id}"


def create_internal_network(ticket_id: str) -> str:
    name = network_name(ticket_id)
    if not _run_ok(["network", "inspect", name]):
        _run(["network", "create", "--internal", name])
    return name


def remove_network(name: str) -> None:
    subprocess.run(["docker", "network", "rm", name], capture_output=True, text=True)


def run_proxy(ticket_id: str, config: SandboxConfig, squid_conf_host_path: str) -> str:
    name = proxy_name(ticket_id)
    net = network_name(ticket_id)
    remove_container(name)
    _run(
        [
            "run",
            "-d",
            "--name",
            name,
            "--network",
            net,
            "--label",
            f"agent-factory-sandbox={ticket_id}",
            "-v",
            f"{squid_conf_host_path}:/etc/squid/squid.conf:ro",
            config.proxy_image,
        ]
    )
    # Second leg: attach the proxy to the default bridge so it can actually reach
    # the internet on behalf of allow-listed requests from the fully-internal network.
    _run(["network", "connect", "bridge", name])
    wait_until_execable(name)
    # Being exec-able only means the container's shell is up, not that squid itself
    # has finished initializing and bound its port — confirm that precisely, since a
    # curl racing ahead of it produces zero squid log entries at all (not even a deny).
    wait_until_port_listening(name, 3128)
    return name


def wait_until_execable(name: str, attempts: int = 30, delay: float = 0.5) -> None:
    """Block until `docker exec` against this container actually works.

    `docker run -d` returns as soon as the container is *created*, not once its
    process is far enough along to accept exec — on a loaded CI runner that gap
    is wide enough for a `docker exec` racing right behind it to fail outright.
    """
    for _ in range(attempts):
        if _run_ok(["exec", name, "true"]):
            return
        time.sleep(delay)
    raise RuntimeError(f"container {name} never became exec-able")


def wait_until_port_listening(name: str, port: int, attempts: int = 30, delay: float = 0.5) -> None:
    """Block until the process inside `name` is actually bound to `port`.

    Checks /proc/net/tcp{,6} directly rather than relying on ss/netstat/curl being
    installed in the image — those column-format files are always present on Linux.
    """
    hex_port = format(port, "04X")
    probe = f"cat /proc/net/tcp /proc/net/tcp6 2>/dev/null | grep -qi ':{hex_port} '"
    for _ in range(attempts):
        result = subprocess.run(
            ["docker", "exec", name, "sh", "-c", probe], capture_output=True, text=True
        )
        if result.returncode == 0:
            return
        time.sleep(delay)
    raise RuntimeError(f"{name} never started listening on port {port}")


def run_sandbox(
    ticket_id: str,
    config: SandboxConfig,
    worktree_host_path: str,
    git_token: str,
    extra_mount: tuple[str, str] | None = None,
    extra_env: dict[str, str] | None = None,
    network: str | None = None,
    proxy_url: str | None = None,
) -> str:
    name = sandbox_name(ticket_id)
    net = network if network is not None else network_name(ticket_id)
    resolved_proxy_url = proxy_url if proxy_url is not None else f"http://{proxy_name(ticket_id)}:3128"
    remove_container(name)
    args = [
        "run",
        "-d",
        "--name",
        name,
        "--network",
        net,
        "--label",
        f"agent-factory-sandbox={ticket_id}",
        "--cpus",
        str(config.limits.cpus),
        "--memory",
        config.limits.memory,
        "--read-only",
        "--tmpfs",
        f"/tmp:size={config.limits.workspace_size}",
        "--tmpfs",
        f"/home/sandbox:size={config.limits.workspace_size},uid=10001,gid=10001",
        "--security-opt",
        "no-new-privileges",
        "-e",
        f"HTTP_PROXY={resolved_proxy_url}",
        "-e",
        f"HTTPS_PROXY={resolved_proxy_url}",
        "-e",
        "NO_PROXY=localhost,127.0.0.1",
        "-e",
        f"AGENT_FACTORY_TICKET_ID={ticket_id}",
        "-e",
        f"AGENT_FACTORY_GIT_TOKEN={git_token}",
        "-v",
        f"{worktree_host_path}:/workspace/repo",
    ]
    if extra_mount is not None:
        host_path, container_path = extra_mount
        args += ["-v", f"{host_path}:{container_path}"]
    # T-204: caller-supplied secrets (e.g. a BYOK ANTHROPIC_API_KEY) scoped to this
    # single container's env only — never written to disk, never in this function's
    # own argv-visible parts beyond the "-e" pairs docker itself requires.
    if extra_env is not None:
        for key, value in extra_env.items():
            args += ["-e", f"{key}={value}"]
    args.append(config.image)
    _run(args)
    return name


def exec_in(container: str, cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", "exec", container, *cmd], capture_output=True, text=True)


def exec_stream(
    container: str, cmd: list[str], env: dict[str, str] | None = None
) -> Iterator[str]:
    """Stream stdout lines from a command run inside an already-running container.

    T-204: the orchestrator's real dev-agent run execs `claude` this way instead of
    spawning it as a bare host subprocess (`claude_runner.py`'s pre-T-204 behavior).
    `env` is passed via `docker exec -e` (per-invocation, never written to the
    container's own persistent env, never logged) — same secret-handling discipline as
    `run_sandbox`'s `extra_env`.
    """
    args = ["docker", "exec", "-i"]
    if env:
        for key, value in env.items():
            args += ["-e", f"{key}={value}"]
    args += [container, *cmd]
    process = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    assert process.stdout is not None
    try:
        yield from process.stdout
    finally:
        if process.poll() is None:
            process.terminate()


def remove_container(name: str) -> None:
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True)


def container_exists(name: str) -> bool:
    return _run_ok(["inspect", name])


def network_exists(name: str) -> bool:
    return _run_ok(["network", "inspect", name])
