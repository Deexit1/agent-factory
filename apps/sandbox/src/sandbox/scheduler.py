"""T-204 (SPEC-204 AC2): real mutual-exclusion placement over a fixed pool of logical
"VM slots", scoped to today's actual deployment shape — one orchestrator process, one
host (`docs/06-tech-stack.md`'s own Phase-2 activation note: a second runner VM is the
plan until sustained parallel tickets exceed 5; there is no multi-host coordination
problem to solve for real yet). True cross-host/cross-process coordination (Postgres
advisory locks, Redis) is a disclosed gap, deferred to whenever the "Runner pool ->
Kubernetes" activation fires — not silently faked here.

The guarantee this enforces: two DIFFERENT orgs' leases can never hold the same slot at
the same instant. See tests/unit/test_scheduler_property.py for the 100-run concurrent
proof.
"""

import threading
import time
from dataclasses import dataclass


class NoSlotAvailable(Exception):
    pass


@dataclass(frozen=True)
class SlotLease:
    slot_id: int
    org_id: str
    ticket_id: str


class HostPool:
    def __init__(self, host_slots: int) -> None:
        if host_slots < 1:
            raise ValueError("host_slots must be >= 1")
        self._host_slots = host_slots
        self._lock = threading.Lock()
        self._occupied: dict[int, SlotLease] = {}

    def acquire(
        self, *, org_id: str, ticket_id: str, timeout_s: float = 30.0, poll_interval_s: float = 0.01
    ) -> SlotLease:
        deadline = time.monotonic() + timeout_s
        while True:
            with self._lock:
                for slot_id in range(self._host_slots):
                    if slot_id not in self._occupied:
                        lease = SlotLease(slot_id=slot_id, org_id=org_id, ticket_id=ticket_id)
                        self._occupied[slot_id] = lease
                        return lease
            if time.monotonic() > deadline:
                raise NoSlotAvailable(
                    f"no free slot among {self._host_slots} within {timeout_s}s"
                )
            time.sleep(poll_interval_s)

    def release(self, lease: SlotLease) -> None:
        with self._lock:
            current = self._occupied.get(lease.slot_id)
            if current is not None and current.ticket_id == lease.ticket_id:
                del self._occupied[lease.slot_id]

    def snapshot(self) -> dict[int, SlotLease]:
        with self._lock:
            return dict(self._occupied)
