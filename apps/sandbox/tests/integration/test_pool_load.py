"""SPEC-204 AC4: "pre-warmed pool keeps p95 sandbox-ready time < 30s under the load
test." Real Docker required (see conftest.py's `_images_built` session fixture, which
this whole integration package already assumes, same as test_sandbox_lifecycle.py)."""

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sandbox import docker_runtime
from sandbox.config import SandboxConfig
from sandbox.pool import SandboxPool
from sandbox.runtime import DockerRuntime

POOL_SIZE = 3
CONCURRENT_REQUESTS = 10
P95_BUDGET_S = 30.0


def _acquire_and_wait_ready(
    pool: SandboxPool, org_id: str, ticket_id: str, worktree: Path
) -> float:
    start = time.monotonic()
    name = pool.acquire_for(
        org_id=org_id,
        ticket_id=ticket_id,
        worktree_host_path=str(worktree),
        allowed_domains=["pypi.org"],
    )
    docker_runtime.wait_until_execable(name)
    return time.monotonic() - start


def test_prewarmed_pool_p95_ready_time_under_30s(tmp_path: Path) -> None:
    config = SandboxConfig()
    pool = SandboxPool(
        runtime=DockerRuntime(),
        config=config,
        pool_size=POOL_SIZE,
        state_root=tmp_path / "pool-state",
    )
    pool.warm()

    worktrees = []
    for i in range(CONCURRENT_REQUESTS):
        wt = tmp_path / f"wt-{i}"
        wt.mkdir()
        (wt / "README.md").write_text("hello\n")
        worktrees.append(wt)

    ticket_ids = [f"loadT{i}" for i in range(CONCURRENT_REQUESTS)]
    try:
        with ThreadPoolExecutor(max_workers=CONCURRENT_REQUESTS) as pool_exec:
            futures = [
                pool_exec.submit(
                    _acquire_and_wait_ready, pool, f"org-{i % 3}", ticket_ids[i], worktrees[i]
                )
                for i in range(CONCURRENT_REQUESTS)
            ]
            durations = sorted(f.result() for f in futures)

        p95_index = max(0, int(len(durations) * 0.95) - 1)
        p95 = durations[p95_index]
        assert p95 < P95_BUDGET_S, f"p95={p95:.1f}s over budget; durations={durations}"
    finally:
        for ticket_id in ticket_ids:
            pool.release(ticket_id)
