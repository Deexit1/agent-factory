import os
import shutil
import stat
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

HOOK_SOURCE = Path(__file__).resolve().parents[2] / "hooks" / "pre-push"


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(args)}\n{result.stderr}")
    return result


def ensure_bare_clone(repo_url: str, cache_dir: Path) -> Path:
    """A local bare mirror used as a fast clone source — not bind-mounted anywhere."""
    bare_path = cache_dir / "upstream.git"
    if bare_path.exists():
        _run(["git", "fetch", "--all"], cwd=bare_path)
    else:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "--bare", repo_url, str(bare_path)])
    return bare_path


def add_worktree(
    bare_path: Path, worktree_path: Path, ticket_id: str, base_branch: str, origin_url: str
) -> Path:
    """A full, self-contained clone checked out on refs/heads/agent/<ticket_id>.

    Not a literal `git worktree add`: a worktree's .git file points back at the
    main repo's git dir by absolute host path, which breaks once this directory
    is bind-mounted into a container with its own filesystem namespace. A full
    clone is self-contained and portable to bind-mount anywhere.
    """
    remove_worktree(worktree_path)
    branch = f"agent/{ticket_id}"

    _run(["git", "clone", "--branch", base_branch, str(bare_path), str(worktree_path)])
    _run(["git", "checkout", "-b", branch], cwd=worktree_path)
    _run(["git", "remote", "set-url", "origin", origin_url], cwd=worktree_path)
    make_writable_by_any_user(worktree_path)
    _install_pre_push_hook(worktree_path)
    return worktree_path


def make_writable_by_any_user(path: Path) -> None:
    """Clone is created on the host as the host's user; the sandbox container runs
    as a different, fixed uid. Docker Desktop's bind-mount layer doesn't enforce real
    UID/GID checks so this is invisible on Windows/Mac, but native Linux (CI, prod)
    does — without this, `git push` inside the container fails to write .git/refs
    lock files with "Permission denied". Safe here: an ephemeral, single-tenant,
    per-ticket directory that only this one sandbox ever touches.
    """
    path.chmod(path.stat().st_mode | 0o777)
    for item in path.rglob("*"):
        try:
            # OR in rw(x) rather than overwrite: preserves existing executable bits
            # (e.g. scripts checked into the repo), just widens who can use them.
            mode = 0o777 if item.is_dir() else 0o666
            item.chmod(item.stat().st_mode | mode)
        except OSError:
            pass


def _install_pre_push_hook(worktree_path: Path) -> None:
    hooks_dir = worktree_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    target = hooks_dir / "pre-push"
    # Binary copy: Path.write_text() on Windows re-translates "\n" to "\r\n",
    # which corrupts the shebang line and breaks exec() inside the Linux container.
    target.write_bytes(HOOK_SOURCE.read_bytes())
    target.chmod(0o755)


def _clear_readonly_and_retry(func: Callable[[str], Any], path: str, _exc: BaseException) -> None:
    # Git marks object files read-only; on Windows that blocks deletion outright
    # (unlike POSIX, where owning the parent directory is enough).
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_worktree(worktree_path: Path) -> None:
    if not worktree_path.exists():
        return
    shutil.rmtree(worktree_path, onexc=_clear_readonly_and_retry)
