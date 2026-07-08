from orchestrator.github_client import GhCliGitHubClient


class _FakeCompleted:
    returncode = 0
    stdout = "https://github.com/example/repo/pull/1\n"
    stderr = ""


def test_env_is_none_when_no_token_set() -> None:
    client = GhCliGitHubClient()
    assert client._env() is None  # noqa: SLF001


def test_env_overrides_github_token_when_token_set() -> None:
    client = GhCliGitHubClient(token="ghs_fake_installation_token")
    env = client._env()  # noqa: SLF001
    assert env is not None
    assert env["GITHUB_TOKEN"] == "ghs_fake_installation_token"


def test_open_pr_passes_the_scoped_env_to_subprocess(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = []
    monkeypatch.setattr("orchestrator.github_client.shutil.which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(
        "orchestrator.github_client.subprocess.run",
        lambda args, **kw: calls.append(kw) or _FakeCompleted(),
    )

    client = GhCliGitHubClient(token="ghs_fake_installation_token")
    client.open_pr(branch="agent/T-203", base="main", title="t", body="b")

    assert calls[0]["env"]["GITHUB_TOKEN"] == "ghs_fake_installation_token"
