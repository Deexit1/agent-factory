from sandbox.egress_proxy import render_squid_conf


def test_render_squid_conf_includes_all_domains_with_leading_dot() -> None:
    conf = render_squid_conf(["pypi.org", ".already-dotted.com"])

    assert "acl allowed_dst dstdomain .pypi.org .already-dotted.com" in conf


def test_render_squid_conf_default_denies() -> None:
    conf = render_squid_conf(["pypi.org"])

    assert "http_access deny all" in conf
    assert conf.strip().endswith("cache deny all")


def test_render_squid_conf_logs_every_request() -> None:
    conf = render_squid_conf(["pypi.org"])

    assert "access_log stdio:/var/log/squid/access.log agent_factory" in conf
