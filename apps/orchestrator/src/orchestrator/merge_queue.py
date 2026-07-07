"""Merge-queue processor (SPEC-106): a callable entry point (no auto-dispatch,
matching every other agent in this repo — Planner/Delivery Manager/dev agent/
Review agent are all invoked by tests/an ops script, not triggered automatically)
that processes one repo's queued merge entries strictly in FIFO order. The
ordering itself IS the serialization — no locking primitive is needed since the
orchestrator drives entries one at a time, sequentially.

Real GitHub-native merge queue (or a bors-style bot) is deliberately not used
here — that requires GitHub org/repo admin configuration this session has no
reason to assume exists, and would be unverifiable from here either way. This
module is the disclosed, home-grown substitute.
"""

import os
import shutil
import stat
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from schemas import DEFAULT_REPO

from orchestrator import git_ops
from orchestrator.api_client import ApiClient
from orchestrator.github_client import GitHubClient

MERGE_QUEUE_ACTOR = "system:merge-queue"


def _clear_readonly_and_retry(func: Callable[[str], None], path: str, _exc_info: object) -> None:
    # Git marks some object files read-only; a plain rmtree silently leaves them
    # behind on Windows (even with ignore_errors=True) instead of raising loudly.
    os.chmod(path, stat.S_IWRITE)
    func(path)


@dataclass(frozen=True)
class MergeQueueEntryResult:
    ticket_id: str
    outcome: str  # "merged" | "conflict"
    conflicting_paths: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MergeQueueResult:
    processed: list[MergeQueueEntryResult] = field(default_factory=list)


def run_merge_queue(
    *,
    api: ApiClient,
    github: GitHubClient,
    repo_url: str,
    workspace_root: Path,
    repo: str = DEFAULT_REPO,
    base_branch: str = "main",
) -> MergeQueueResult:
    entries = api.list_merge_queue_entries(repo=repo)
    processed: list[MergeQueueEntryResult] = []

    for entry in entries:
        ticket_id = entry["ticket_id"]
        branch = f"agent/{ticket_id}"
        scratch = workspace_root / f"merge-{ticket_id}"

        git_ops.clone_branch(repo_url, branch, scratch)
        try:
            success, conflicting_paths = git_ops.rebase_onto(scratch, base_branch)

            if success:
                git_ops.force_push(scratch, branch)
                pr = github.get_pr_for_branch(branch)
                github.merge_pr(pr)
                api.resolve_merge_success(entry["id"], actor=MERGE_QUEUE_ACTOR)
                processed.append(MergeQueueEntryResult(ticket_id, "merged"))
            else:
                api.resolve_merge_conflict(
                    entry["id"], actor=MERGE_QUEUE_ACTOR, conflicting_paths=conflicting_paths
                )
                processed.append(MergeQueueEntryResult(ticket_id, "conflict", conflicting_paths))
        finally:
            shutil.rmtree(scratch, onexc=_clear_readonly_and_retry)

    return MergeQueueResult(processed=processed)
