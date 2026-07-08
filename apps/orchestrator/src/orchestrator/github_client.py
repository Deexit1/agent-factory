import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field, replace
from typing import Protocol


@dataclass(frozen=True)
class PullRequest:
    url: str
    number: int


class GitHubClient(Protocol):
    def open_pr(self, *, branch: str, base: str, title: str, body: str) -> PullRequest: ...
    def get_pr_diff(self, pr: PullRequest) -> str: ...
    def post_comment(self, pr: PullRequest, body: str) -> None: ...
    def get_pr_for_branch(self, branch: str) -> PullRequest: ...
    def merge_pr(self, pr: PullRequest) -> None: ...
    def with_token(self, token: str | None) -> "GitHubClient":
        """T-203: return a client scoped to a per-ticket minted installation token —
        never mutates the caller's original instance."""
        ...


@dataclass
class GhCliGitHubClient:
    """Real implementation: shells out to the `gh` CLI. Not exercised by tests per the
    project's decision to stub PR creation — no scratch GitHub repo is available here.

    T-203: `token`, when set, scopes every `gh` invocation to a per-ticket minted
    GitHub App installation token via a subprocess-local `GITHUB_TOKEN` env override —
    the same `Popen(env=...)` pattern claude_runner.py established for BYOK keys
    (T-202), never argv, never a log line. `None` (the default, every pre-T-203/
    dogfood call site) preserves today's ambient-`GITHUB_TOKEN` behavior exactly.
    """

    token: str | None = None

    def with_token(self, token: str | None) -> "GhCliGitHubClient":
        return replace(self, token=token)

    def _env(self) -> dict[str, str] | None:
        return {**os.environ, "GITHUB_TOKEN": self.token} if self.token else None

    def open_pr(self, *, branch: str, base: str, title: str, body: str) -> PullRequest:
        gh_bin = shutil.which("gh")
        if gh_bin is None:
            raise RuntimeError("gh CLI not found on PATH")

        result = subprocess.run(
            [
                gh_bin,
                "pr",
                "create",
                "--head",
                branch,
                "--base",
                base,
                "--title",
                title,
                "--body",
                body,
            ],
            env=self._env(),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"gh pr create failed:\n{result.stderr}")

        url = result.stdout.strip().splitlines()[-1]
        number = int(url.rstrip("/").rsplit("/", 1)[-1])
        return PullRequest(url=url, number=number)

    def get_pr_diff(self, pr: PullRequest) -> str:
        gh_bin = shutil.which("gh")
        if gh_bin is None:
            raise RuntimeError("gh CLI not found on PATH")
        result = subprocess.run(
            [gh_bin, "pr", "diff", str(pr.number)],
            env=self._env(),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"gh pr diff failed:\n{result.stderr}")
        return result.stdout

    def post_comment(self, pr: PullRequest, body: str) -> None:
        gh_bin = shutil.which("gh")
        if gh_bin is None:
            raise RuntimeError("gh CLI not found on PATH")
        result = subprocess.run(
            [gh_bin, "pr", "comment", str(pr.number), "--body", body],
            env=self._env(),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"gh pr comment failed:\n{result.stderr}")

    def get_pr_for_branch(self, branch: str) -> PullRequest:
        gh_bin = shutil.which("gh")
        if gh_bin is None:
            raise RuntimeError("gh CLI not found on PATH")
        result = subprocess.run(
            [gh_bin, "pr", "view", branch, "--json", "url,number"],
            env=self._env(),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"gh pr view failed:\n{result.stderr}")
        data = json.loads(result.stdout)
        return PullRequest(url=data["url"], number=data["number"])

    def merge_pr(self, pr: PullRequest) -> None:
        gh_bin = shutil.which("gh")
        if gh_bin is None:
            raise RuntimeError("gh CLI not found on PATH")
        result = subprocess.run(
            [gh_bin, "pr", "merge", str(pr.number), "--squash"],
            env=self._env(),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"gh pr merge failed:\n{result.stderr}")


@dataclass
class FakeGitHubClient:
    """Test double: records calls instead of hitting the real GitHub API.

    `repo_url`, if set, makes `merge_pr` perform a REAL git push of the PR's
    branch onto `main` in that repo — a test-only substitute for what GitHub's
    real merge would do. Needed by merge_queue.py's tests: the whole point of
    those tests is proving a SECOND ticket's rebase genuinely conflicts against
    a FIRST ticket's real merge, which only happens if something actually
    updates `main` — a pure no-op recording call wouldn't move the goalposts a
    second ticket's rebase is checked against.
    """

    calls: list[dict[str, str]] = field(default_factory=list)
    comments: list[dict[str, str]] = field(default_factory=list)
    merged: list[int] = field(default_factory=list)
    next_pr_number: int = 1
    diff: str = ""
    repo_url: str | None = None
    # T-203: records the token run_dev_agent threaded through, if any — tests can
    # assert on this without this fake needing to do anything real with it.
    last_token: str | None = None

    def __post_init__(self) -> None:
        self._prs_by_branch: dict[str, PullRequest] = {}
        self._branch_by_pr_number: dict[int, str] = {}

    def with_token(self, token: str | None) -> "FakeGitHubClient":
        # Deliberately returns self, not a copy — tests hold a reference to the
        # original instance and assert on its .calls/.comments/.merged afterward; a
        # replace()'d copy would silently break that tracking.
        self.last_token = token
        return self

    def open_pr(self, *, branch: str, base: str, title: str, body: str) -> PullRequest:
        self.calls.append({"branch": branch, "base": base, "title": title, "body": body})
        pr = PullRequest(
            url=f"https://github.com/example/repo/pull/{self.next_pr_number}",
            number=self.next_pr_number,
        )
        self._prs_by_branch[branch] = pr
        self._branch_by_pr_number[pr.number] = branch
        self.next_pr_number += 1
        return pr

    def get_pr_diff(self, pr: PullRequest) -> str:
        return self.diff

    def post_comment(self, pr: PullRequest, body: str) -> None:
        self.comments.append({"pr_number": str(pr.number), "body": body})

    def get_pr_for_branch(self, branch: str) -> PullRequest:
        if branch not in self._prs_by_branch:
            raise RuntimeError(f"no PR ever opened for branch {branch!r}")
        return self._prs_by_branch[branch]

    def merge_pr(self, pr: PullRequest) -> None:
        self.merged.append(pr.number)
        if self.repo_url is None:
            return
        branch = self._branch_by_pr_number[pr.number]
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                ["git", "clone", "--quiet", "--branch", branch, self.repo_url, tmp],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "push", "-q", "origin", "HEAD:main"],
                cwd=tmp,
                check=True,
                capture_output=True,
            )
