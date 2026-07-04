import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from sandbox import credential_broker, docker_runtime, worktree
from sandbox.config import SandboxConfig, state_dir_for
from sandbox.egress_proxy import render_squid_conf

_REMOTE_SCHEMES = {"http", "https", "git", "ssh"}


def _is_remote_url(repo_url: str) -> bool:
    return urlparse(repo_url).scheme in _REMOTE_SCHEMES


def _state_path(ticket_id: str) -> Path:
    return state_dir_for(ticket_id) / "state.json"


def _save_state(ticket_id: str, state: dict[str, object]) -> None:
    path = _state_path(ticket_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


def _load_state(ticket_id: str) -> dict[str, object] | None:
    path = _state_path(ticket_id)
    if not path.exists():
        return None
    result: dict[str, object] = json.loads(path.read_text())
    return result


def up(ticket_id: str, repo_url: str, base_branch: str, config: SandboxConfig) -> None:
    state_dir = state_dir_for(ticket_id)
    state_dir.mkdir(parents=True, exist_ok=True)

    cache_dir = state_dir / "cache"
    bare_path = worktree.ensure_bare_clone(repo_url, cache_dir)
    worktree_path = state_dir / "worktree"

    if _is_remote_url(repo_url):
        origin_url = repo_url
        extra_mount = None
    else:
        # Local testing only (repo_url is a filesystem path, e.g. in tests): a host
        # path is meaningless inside the container, so bind-mount the local bare
        # cache itself as the in-container "remote" pushes go to. Real deployments
        # pass a real git host URL here, reachable via the egress proxy allow-list,
        # and this branch never triggers.
        origin_url = "/mnt/upstream.git"
        extra_mount = (str(bare_path), "/mnt/upstream.git")

    worktree.add_worktree(bare_path, worktree_path, ticket_id, base_branch, origin_url)

    credential = credential_broker.issue(ticket_id)

    docker_runtime.create_internal_network(ticket_id)

    squid_conf_path = state_dir / "squid.conf"
    squid_conf_path.write_text(render_squid_conf(config.allowed_domains))
    docker_runtime.run_proxy(ticket_id, config, str(squid_conf_path))

    docker_runtime.run_sandbox(
        ticket_id, config, str(worktree_path), credential.token, extra_mount=extra_mount
    )

    forwarder = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "sandbox.egress_forwarder",
            ticket_id,
            docker_runtime.proxy_name(ticket_id),
            config.api_url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    _save_state(
        ticket_id,
        {
            "repo_url": repo_url,
            "bare_path": str(bare_path),
            "worktree_path": str(worktree_path),
            "forwarder_pid": forwarder.pid,
        },
    )

    print(f"sandbox up: {docker_runtime.sandbox_name(ticket_id)} ready")


def _kill(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        # Already exited, or the platform's signal delivery doesn't apply
        # (e.g. Windows raises a generic OSError, not ProcessLookupError).
        pass


def down(ticket_id: str) -> None:
    state = _load_state(ticket_id)

    docker_runtime.remove_container(docker_runtime.sandbox_name(ticket_id))
    docker_runtime.remove_container(docker_runtime.proxy_name(ticket_id))
    docker_runtime.remove_network(docker_runtime.network_name(ticket_id))

    if state is not None:
        forwarder_pid = state.get("forwarder_pid")
        if isinstance(forwarder_pid, int):
            _kill(forwarder_pid)

        worktree_path = state.get("worktree_path")
        if isinstance(worktree_path, str):
            worktree.remove_worktree(Path(worktree_path))

    credential_broker.revoke(ticket_id)
    _state_path(ticket_id).unlink(missing_ok=True)

    print(f"sandbox down: {ticket_id} torn down")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="sandbox")
    subparsers = parser.add_subparsers(dest="command", required=True)

    up_parser = subparsers.add_parser("up", help="Provision a sandbox for a ticket")
    up_parser.add_argument("ticket_id")
    up_parser.add_argument("--repo", required=True, dest="repo_url")
    up_parser.add_argument("--base-branch", default="main")
    up_parser.add_argument("--api-url", default="http://localhost:8000")

    down_parser = subparsers.add_parser("down", help="Tear down a sandbox for a ticket")
    down_parser.add_argument("ticket_id")

    args = parser.parse_args(argv)

    if args.command == "up":
        config = SandboxConfig(api_url=args.api_url)
        up(args.ticket_id, args.repo_url, args.base_branch, config)
    elif args.command == "down":
        down(args.ticket_id)


if __name__ == "__main__":
    main()
