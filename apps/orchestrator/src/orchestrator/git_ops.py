import base64
import subprocess
from pathlib import Path

from schemas.branches import AGENT_BRANCH_PREFIX


class BranchNotAllowed(Exception):
    def __init__(self, branch: str) -> None:
        self.branch = branch
        super().__init__(
            f"refusing to push to {branch!r}; only {AGENT_BRANCH_PREFIX}* branches are allowed"
        )


def _assert_agent_branch(branch: str) -> None:
    """T-203 (SPEC-203 AC1): the real, live-testable half of "push to the default
    branch is impossible" — enforced in our own code, before any subprocess or network
    call, independent of whatever GitHub-side branch protection is (or isn't)
    configured on the customer's repo."""
    if not branch.startswith(AGENT_BRANCH_PREFIX):
        raise BranchNotAllowed(branch)


def build_auth_header(token: str) -> str:
    """T-203: a per-invocation `git -c http.extraheader=...` value for a minted GitHub
    App installation token — never written to `.git/config` (unlike URL-embedding),
    never argv-visible in a process listing beyond this one git invocation, never
    logged. `None` (every pre-T-203 call site) preserves ambient git-credential
    behavior exactly."""
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return f"AUTHORIZATION: basic {basic}"


def _auth_args(auth_header: str | None) -> list[str]:
    return ["-c", f"http.extraheader={auth_header}"] if auth_header else []


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(args)}\n{result.stderr}")
    return result


def clone_branch(
    repo_url: str, branch: str, dest: Path, *, auth_header: str | None = None
) -> None:
    result = subprocess.run(
        [
            "git",
            *_auth_args(auth_header),
            "clone",
            "--quiet",
            "--branch",
            branch,
            repo_url,
            str(dest),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git clone --branch {branch} failed:\n{result.stderr}")

    # A rebase that must replay a commit (create a new commit object with a new
    # parent) needs a committer identity, same as any other commit — a bare
    # environment with no global git config (a fresh CI runner, a minimal
    # container) has none. Setting it locally here means the merge-queue never
    # depends on whatever identity happens to be configured on the machine it
    # runs on.
    _run(["git", "config", "user.email", "merge-queue@agent-factory.local"], dest)
    _run(["git", "config", "user.name", "Agent Factory Merge Queue"], dest)


def has_uncommitted_changes(workspace_dir: Path) -> bool:
    result = _run(["git", "status", "--porcelain"], workspace_dir)
    return bool(result.stdout.strip())


def commit_all(workspace_dir: Path, message: str) -> None:
    _run(["git", "add", "-A"], workspace_dir)
    _run(["git", "commit", "-q", "-m", message], workspace_dir)


def push(workspace_dir: Path, branch: str, *, auth_header: str | None = None) -> None:
    _assert_agent_branch(branch)
    _run(
        ["git", *_auth_args(auth_header), "push", "origin", f"HEAD:{branch}"],
        workspace_dir,
    )


def force_push(workspace_dir: Path, branch: str, *, auth_header: str | None = None) -> None:
    """Post-rebase push — history was rewritten, a plain push would be refused.
    `--force-with-lease` still refuses if someone else pushed to this branch in
    the meantime (unlike a bare `--force`)."""
    _assert_agent_branch(branch)
    _run(
        [
            "git",
            *_auth_args(auth_header),
            "push",
            "--force-with-lease",
            "origin",
            f"HEAD:{branch}",
        ],
        workspace_dir,
    )


def diff_against(workspace_dir: Path, base_ref: str) -> str:
    result = _run(["git", "diff", base_ref], workspace_dir)
    return result.stdout


def rebase_onto(
    workspace_dir: Path, base_branch: str, *, auth_header: str | None = None
) -> tuple[bool, list[str]]:
    """SPEC-106: fetch and rebase the current branch onto `origin/{base_branch}`.

    Returns `(success, conflicting_paths)` — a conflict is an expected outcome
    here, not a bug, so this is the one git_ops function that deliberately does
    NOT raise on a git command's non-zero exit; it aborts the rebase and reports
    the conflicting paths instead."""
    _run(["git", *_auth_args(auth_header), "fetch", "origin", base_branch], workspace_dir)
    result = subprocess.run(
        ["git", "rebase", f"origin/{base_branch}"],
        cwd=workspace_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True, []

    conflicts = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        cwd=workspace_dir,
        capture_output=True,
        text=True,
    )
    conflicting_paths = [p.strip() for p in conflicts.stdout.splitlines() if p.strip()]
    subprocess.run(["git", "rebase", "--abort"], cwd=workspace_dir, capture_output=True, text=True)

    if not conflicting_paths:
        # The rebase failed but nothing is actually in conflict — a real error
        # (bad identity, corrupt object, disk full, ...), not the expected
        # "two branches touched the same lines" outcome this function exists to
        # handle. Silently reporting this as an empty conflict would hide a real
        # bug behind a plausible-looking bounce, exactly like it did before this
        # comment existed.
        raise RuntimeError(
            f"git rebase onto {base_branch} failed with no conflicting paths:\n{result.stderr}"
        )

    return False, conflicting_paths
