from sandbox.egress_forwarder import parse_domain, parse_line


def test_parse_domain_from_connect_method() -> None:
    assert parse_domain("CONNECT", "pypi.org:443") == "pypi.org"


def test_parse_domain_from_get_url() -> None:
    assert parse_domain("GET", "http://blocked.example.com/path") == "blocked.example.com"


def test_parse_line_allowed_connect() -> None:
    event = parse_line("1783148069.271 172.18.0.3 TCP_TUNNEL/200 CONNECT pypi.org:443")

    assert event == {
        "egress": "pypi.org",
        "url": "pypi.org:443",
        "method": "CONNECT",
        "http_status": "200",
        "allowed": True,
        "client_ip": "172.18.0.3",
    }


def test_parse_line_denied_connect() -> None:
    event = parse_line("1783148069.276 172.18.0.3 TCP_DENIED/403 CONNECT blocked.example.com:443")

    assert event is not None
    assert event["allowed"] is False
    assert event["egress"] == "blocked.example.com"


def test_parse_line_returns_none_for_malformed_line() -> None:
    assert parse_line("not enough fields") is None
