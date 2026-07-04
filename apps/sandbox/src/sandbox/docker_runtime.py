import subprocess

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
    return name


def run_sandbox(
    ticket_id: str,
    config: SandboxConfig,
    worktree_host_path: str,
    git_token: str,
    extra_mount: tuple[str, str] | None = None,
) -> str:
    name = sandbox_name(ticket_id)
    net = network_name(ticket_id)
    proxy_url = f"http://{proxy_name(ticket_id)}:3128"
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
        f"HTTP_PROXY={proxy_url}",
        "-e",
        f"HTTPS_PROXY={proxy_url}",
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
    args.append(config.image)
    _run(args)
    return name


def exec_in(container: str, cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", "exec", container, *cmd], capture_output=True, text=True)


def remove_container(name: str) -> None:
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True)


def container_exists(name: str) -> bool:
    return _run_ok(["inspect", name])


def network_exists(name: str) -> bool:
    return _run_ok(["network", "inspect", name])
