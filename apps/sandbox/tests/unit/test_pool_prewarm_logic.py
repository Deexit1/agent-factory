"""Pool bookkeeping proved with a fake runtime double — no Docker needed. The
Docker-gated load test (tests/integration/test_pool_load.py) proves the real p95
latency claim (SPEC-204 AC4); this file proves `SandboxPool`'s own control flow:
warm-up parallelism, fast-path reuse, cold-path fallback, and org-scoped egress
rewriting on hand-out."""

import threading

from sandbox.config import SandboxConfig
from sandbox.pool import SandboxPool


class FakeRuntime:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.networks_created: list[str] = []
        self.proxies_run: list[str] = []
        self.sandboxes_run: list[str] = []
        self.reconfigured: list[str] = []

    def create_network(self, ticket_id: str) -> str:
        with self.lock:
            self.networks_created.append(ticket_id)
        return f"net-{ticket_id}"

    def run_proxy(self, ticket_id: str, config: SandboxConfig, squid_conf_host_path: str) -> str:
        with self.lock:
            self.proxies_run.append(ticket_id)
        return f"proxy-{ticket_id}"

    def run_sandbox(
        self,
        ticket_id,
        config,
        worktree_host_path,
        git_token,
        extra_mount=None,
        extra_env=None,
        network=None,
        proxy_url=None,
    ) -> str:
        with self.lock:
            self.sandboxes_run.append(ticket_id)
        return f"sandbox-{ticket_id}"

    def exec_in(self, container: str, cmd: list[str]):
        if "reconfigure" in cmd:
            with self.lock:
                self.reconfigured.append(container)

        class _Result:
            returncode = 0

        return _Result()

    def exec_stream(self, container, cmd, env=None):
        yield from ()

    def teardown(self, ticket_id: str) -> None:
        pass


def _pool(tmp_path, pool_size: int = 2) -> tuple[SandboxPool, FakeRuntime]:
    runtime = FakeRuntime()
    config = SandboxConfig()
    pool = SandboxPool(
        runtime=runtime, config=config, pool_size=pool_size, state_root=tmp_path
    )
    return pool, runtime


def test_warm_creates_pool_size_idle_slots(tmp_path) -> None:
    pool, runtime = _pool(tmp_path, pool_size=3)
    pool.warm()
    assert len(pool._idle) == 3
    assert len(runtime.networks_created) == 3
    assert len(runtime.proxies_run) == 3


def test_acquire_reuses_a_warm_slot_and_reconfigures_egress(tmp_path) -> None:
    pool, runtime = _pool(tmp_path, pool_size=1)
    pool.warm()
    assert len(pool._idle) == 1

    name = pool.acquire_for(
        org_id="org-a",
        ticket_id="T-1",
        worktree_host_path="/tmp/wt",
        allowed_domains=["custom.example.com"],
    )
    assert name == "sandbox-T-1"
    assert "T-1" in runtime.sandboxes_run
    # A pre-warmed slot was reused (not a cold fresh network+proxy for this ticket).
    assert len(runtime.networks_created) == 1
    assert len(runtime.proxies_run) == 1
    assert runtime.reconfigured, "expected squid -k reconfigure on the reused proxy"


def test_acquire_falls_back_to_cold_path_when_pool_exhausted(tmp_path) -> None:
    pool, runtime = _pool(tmp_path, pool_size=0)
    pool.acquire_for(
        org_id="org-a",
        ticket_id="T-1",
        worktree_host_path="/tmp/wt",
        allowed_domains=["custom.example.com"],
    )
    # Cold path: a fresh network+proxy got created inline for this ticket.
    assert len(runtime.networks_created) == 1
    assert len(runtime.proxies_run) == 1
    assert not runtime.reconfigured, "cold path renders the list directly, no reconfigure needed"


def test_acquire_replenishes_pool_asynchronously(tmp_path) -> None:
    pool, runtime = _pool(tmp_path, pool_size=1)
    pool.warm()
    pool.acquire_for(
        org_id="org-a", ticket_id="T-1", worktree_host_path="/tmp/wt", allowed_domains=[]
    )
    # Replenishment is async — wait for the background thread to land.
    for _ in range(200):
        with pool._lock:
            if len(pool._idle) == 1:
                break
        threading.Event().wait(0.01)
    assert len(pool._idle) == 1
    assert len(runtime.networks_created) == 2  # 1 initial warm + 1 replenishment
