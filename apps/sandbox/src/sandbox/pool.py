"""T-204 (SPEC-204 AC4): a pre-warmed pool of sandbox networks+proxies.

What's actually slow about provisioning a fresh sandbox is the network create + proxy
container boot (image pull, `wait_until_execable`, `wait_until_port_listening`'s polling
loops) — the sandbox container itself (a slim, already-cached Python image) boots in
roughly a second once Docker has the image locally. So pre-warming targets the
network+proxy pair, not a full ticket-bound container (a specific worktree/org egress
list can't be predicted ahead of a request anyway).

Squid supports a live config reload (`squid -k reconfigure`) without dropping the
container, so a pre-warmed proxy's egress allow-list is rewritten to the requesting
org's actual merged list at hand-out time — the pre-warmed proxy is not stuck serving
whatever list it booted with.
"""

import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from sandbox import docker_runtime
from sandbox.config import SandboxConfig
from sandbox.egress_proxy import render_squid_conf
from sandbox.runtime import SandboxRuntime


@dataclass
class PoolSlot:
    pool_id: str
    network: str
    proxy: str
    squid_conf_path: Path


class SandboxPool:
    def __init__(
        self,
        *,
        runtime: SandboxRuntime,
        config: SandboxConfig,
        pool_size: int,
        state_root: Path,
        base_allowed_domains: list[str] | None = None,
    ) -> None:
        self._runtime = runtime
        self._config = config
        self._pool_size = pool_size
        self._state_root = state_root
        self._base_allowed_domains = base_allowed_domains or list(config.allowed_domains)
        self._lock = threading.Lock()
        self._idle: list[PoolSlot] = []
        self._leased: dict[str, PoolSlot] = {}

    def _prewarm_one(self, allowed_domains: list[str] | None = None) -> PoolSlot:
        pool_id = f"pool-{uuid.uuid4().hex[:10]}"
        squid_conf_path = self._state_root / pool_id / "squid.conf"
        squid_conf_path.parent.mkdir(parents=True, exist_ok=True)
        squid_conf_path.write_text(render_squid_conf(allowed_domains or self._base_allowed_domains))

        network = self._runtime.create_network(pool_id)
        proxy = self._runtime.run_proxy(pool_id, self._config, str(squid_conf_path))
        return PoolSlot(
            pool_id=pool_id, network=network, proxy=proxy, squid_conf_path=squid_conf_path
        )

    def warm(self) -> None:
        """Populate the pool up to `pool_size` idle slots, in parallel."""
        with self._lock:
            missing = self._pool_size - len(self._idle)
        if missing <= 0:
            return
        threads = [threading.Thread(target=self._warm_one) for _ in range(missing)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def _warm_one(self) -> None:
        slot = self._prewarm_one()
        with self._lock:
            self._idle.append(slot)

    def _replenish_async(self) -> None:
        threading.Thread(target=self._warm_one, daemon=True).start()

    def acquire_for(
        self,
        *,
        org_id: str,
        ticket_id: str,
        worktree_host_path: str,
        allowed_domains: list[str],
        git_token: str = "",
        extra_env: dict[str, str] | None = None,
    ) -> str:
        with self._lock:
            slot = self._idle.pop() if self._idle else None

        if slot is None:
            # Cold path: pool exhausted, provision a fresh network+proxy inline,
            # already rendered with this org's real allow-list — slower, but still
            # correct (AC4 is a p95 target, not a hard cap).
            slot = self._prewarm_one(allowed_domains)
        else:
            slot.squid_conf_path.write_text(render_squid_conf(allowed_domains))
            self._runtime.exec_in(slot.proxy, ["squid", "-k", "reconfigure"])
            self._replenish_async()

        merged_env = {**(extra_env or {}), "AGENT_FACTORY_ORG_ID": org_id}
        name = self._runtime.run_sandbox(
            ticket_id,
            self._config,
            worktree_host_path,
            git_token,
            extra_env=merged_env,
            network=slot.network,
            proxy_url=f"http://{slot.proxy}:3128",
        )
        with self._lock:
            self._leased[ticket_id] = slot
        return name

    def release(self, ticket_id: str) -> None:
        """Tear down the ticket's sandbox container and its pool slot's network+proxy.

        Deliberately full teardown, not slot recycling — resetting a slot's squid.conf
        back to the base allow-list and reconfiguring it correctly is more state to get
        right than just provisioning a fresh one, and `_replenish_async` already keeps
        the idle pool topped up in the background.
        """
        with self._lock:
            slot = self._leased.pop(ticket_id, None)
        if slot is None:
            return

        docker_runtime.remove_container(docker_runtime.sandbox_name(ticket_id))
        docker_runtime.remove_container(slot.proxy)
        docker_runtime.remove_network(slot.network)
