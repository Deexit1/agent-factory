from sandbox import credential_broker


def test_issue_then_get_returns_matching_credential(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(credential_broker, "state_dir_for", lambda ticket_id: tmp_path / ticket_id)

    issued = credential_broker.issue("T-900")
    fetched = credential_broker.get("T-900")

    assert fetched == issued
    assert issued.allowed_ref == "refs/heads/agent/T-900"
    assert len(issued.token) > 20


def test_get_returns_none_when_no_credential_issued(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(credential_broker, "state_dir_for", lambda ticket_id: tmp_path / ticket_id)

    assert credential_broker.get("T-901") is None


def test_revoke_deletes_the_credential(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(credential_broker, "state_dir_for", lambda ticket_id: tmp_path / ticket_id)

    credential_broker.issue("T-902")
    credential_broker.revoke("T-902")

    assert credential_broker.get("T-902") is None


def test_revoke_is_idempotent_when_nothing_issued(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(credential_broker, "state_dir_for", lambda ticket_id: tmp_path / ticket_id)

    credential_broker.revoke("T-903")  # must not raise
