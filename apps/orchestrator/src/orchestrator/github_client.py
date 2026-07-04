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


@dataclass
class FakeGitHubClient:
    """Test double: records calls instead of hitting the real GitHub API."""

    calls: list[dict[str, str]] = field(default_factory=list)
    next_pr_number: int = 1

    def open_pr(self, *, branch: str, base: str, title: str, body: str) -> PullRequest:
        self.calls.append({"branch": branch, "base": base, "title": title, "body": body})
        pr = PullRequest(
            url=f"https://github.com/example/repo/pull/{self.next_pr_number}",
            number=self.next_pr_number,
        )
        self.next_pr_number += 1
        return pr
