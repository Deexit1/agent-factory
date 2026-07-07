import subprocess
from pathlib import Path


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(args)}\n{result.stderr}")
    return result


def clone_branch(repo_url: str, branch: str, dest: Path) -> None:
    result = subprocess.run(
        ["git", "clone", "--quiet", "--branch", branch, repo_url, str(dest)],
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


def push(workspace_dir: Path, branch: str) -> None:
    _run(["git", "push", "origin", f"HEAD:{branch}"], workspace_dir)


def force_push(workspace_dir: Path, branch: str) -> None:
    """Post-rebase push — history was rewritten, a plain push would be refused.
    `--force-with-lease` still refuses if someone else pushed to this branch in
    the meantime (unlike a bare `--force`)."""
    _run(["git", "push", "--force-with-lease", "origin", f"HEAD:{branch}"], workspace_dir)


def diff_against(workspace_dir: Path, base_ref: str) -> str:
    result = _run(["git", "diff", base_ref], workspace_dir)
    return result.stdout


def rebase_onto(workspace_dir: Path, base_branch: str) -> tuple[bool, list[str]]:
    """SPEC-106: fetch and rebase the current branch onto `origin/{base_branch}`.

    Returns `(success, conflicting_paths)` — a conflict is an expected outcome
    here, not a bug, so this is the one git_ops function that deliberately does
    NOT raise on a git command's non-zero exit; it aborts the rebase and reports
    the conflicting paths instead."""
    _run(["git", "fetch", "origin", base_branch], workspace_dir)
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
