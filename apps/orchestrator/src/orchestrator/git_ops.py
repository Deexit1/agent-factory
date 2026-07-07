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
    return False, conflicting_paths
