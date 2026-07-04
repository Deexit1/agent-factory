import subprocess
from pathlib import Path


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(args)}\n{result.stderr}")
    return result


def has_uncommitted_changes(workspace_dir: Path) -> bool:
    result = _run(["git", "status", "--porcelain"], workspace_dir)
    return bool(result.stdout.strip())


def commit_all(workspace_dir: Path, message: str) -> None:
    _run(["git", "add", "-A"], workspace_dir)
    _run(["git", "commit", "-q", "-m", message], workspace_dir)


def push(workspace_dir: Path, branch: str) -> None:
    _run(["git", "push", "origin", f"HEAD:{branch}"], workspace_dir)


def diff_against(workspace_dir: Path, base_ref: str) -> str:
    result = _run(["git", "diff", base_ref], workspace_dir)
    return result.stdout
