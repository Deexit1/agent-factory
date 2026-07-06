import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class PullRequest:
    url: str
    number: int


class GitHubClient(Protocol):
    def open_pr(self, *, branch: str, base: str, title: str, body: str) -> PullRequest: ...
    def get_pr_diff(self, pr: PullRequest) -> str: ...
    def post_comment(self, pr: PullRequest, body: str) -> None: ...


class GhCliGitHubClient:
    """Real implementation: shells out to the `gh` CLI. Not exercised by tests per the
    project's decision to stub PR creation — no scratch GitHub repo is available here.
    """

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
            [gh_bin, "pr", "diff", str(pr.number)], capture_output=True, text=True
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
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"gh pr comment failed:\n{result.stderr}")


@dataclass
class FakeGitHubClient:
    """Test double: records calls instead of hitting the real GitHub API."""

    calls: list[dict[str, str]] = field(default_factory=list)
    comments: list[dict[str, str]] = field(default_factory=list)
    next_pr_number: int = 1
    diff: str = ""

    def open_pr(self, *, branch: str, base: str, title: str, body: str) -> PullRequest:
        self.calls.append({"branch": branch, "base": base, "title": title, "body": body})
        pr = PullRequest(
            url=f"https://github.com/example/repo/pull/{self.next_pr_number}",
            number=self.next_pr_number,
        )
        self.next_pr_number += 1
        return pr

    def get_pr_diff(self, pr: PullRequest) -> str:
        return self.diff

    def post_comment(self, pr: PullRequest, body: str) -> None:
        self.comments.append({"pr_number": str(pr.number), "body": body})
