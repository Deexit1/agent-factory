"""SPEC-204 AC2: "two orgs' concurrent tasks never co-locate on one VM (scheduler
property test, 100 runs)". No Docker needed — this is a pure-Python concurrency proof
of `HostPool`'s own mutual-exclusion guarantee, scoped to one process (see
scheduler.py's module docstring for why that's the honest scope today)."""

import random
import threading
import time

import pytest

from sandbox.scheduler import HostPool, NoSlotAvailable

HOST_SLOTS = 3
ORGS = ["org-a", "org-b", "org-c", "org-d"]


def _worker(
    pool: HostPool,
    org_id: str,
    ticket_id: str,
    intervals: list[tuple[int, str, float, float]],
    lock: threading.Lock,
) -> None:
    lease = pool.acquire(org_id=org_id, ticket_id=ticket_id, timeout_s=5.0)
    start = time.monotonic()
    time.sleep(random.uniform(0.001, 0.01))
    end = time.monotonic()
    pool.release(lease)
    with lock:
        intervals.append((lease.slot_id, org_id, start, end))


def _run_one_round(round_no: int) -> list[tuple[int, str, float, float]]:
    pool = HostPool(host_slots=HOST_SLOTS)
    intervals: list[tuple[int, str, float, float]] = []
    lock = threading.Lock()
    threads = [
        threading.Thread(
            target=_worker,
            args=(pool, ORGS[i % len(ORGS)], f"T-{round_no}-{i}", intervals, lock),
        )
        for i in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)
    return intervals


def _assert_no_cross_org_overlap(intervals: list[tuple[int, str, float, float]]) -> None:
    by_slot: dict[int, list[tuple[str, float, float]]] = {}
    for slot_id, org_id, start, end in intervals:
        by_slot.setdefault(slot_id, []).append((org_id, start, end))
    for slot_id, entries in by_slot.items():
        entries.sort(key=lambda e: e[1])
        for (org_a, start_a, end_a), (org_b, start_b, end_b) in zip(
            entries, entries[1:], strict=False
        ):
            assert start_b >= end_a, (
                f"slot {slot_id}: {org_a} [{start_a},{end_a}] overlaps "
                f"{org_b} [{start_b},{end_b}]"
            )


def test_no_cross_org_colocation_across_100_concurrent_rounds() -> None:
    all_intervals: list[tuple[int, str, float, float]] = []
    for round_no in range(100):
        round_intervals = _run_one_round(round_no)
        assert len(round_intervals) == 8, "every worker must have acquired and released"
        _assert_no_cross_org_overlap(round_intervals)
        all_intervals.extend(round_intervals)

    # Prove this is a real shared pool (slots get reused across different orgs over
    # time), not an accidental static one-slot-per-org partitioning that would make the
    # no-overlap assertion above trivially true for the wrong reason.
    orgs_per_slot: dict[int, set[str]] = {}
    for slot_id, org_id, _start, _end in all_intervals:
        orgs_per_slot.setdefault(slot_id, set()).add(org_id)
    assert all(len(orgs) > 1 for orgs in orgs_per_slot.values()), orgs_per_slot


def test_no_slot_available_raises_when_pool_exhausted() -> None:
    pool = HostPool(host_slots=1)
    lease = pool.acquire(org_id="org-a", ticket_id="T-1", timeout_s=1.0)
    try:
        with pytest.raises(NoSlotAvailable):
            pool.acquire(org_id="org-b", ticket_id="T-2", timeout_s=0.1)
    finally:
        pool.release(lease)
