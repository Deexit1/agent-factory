SQUID_CONF_TEMPLATE = """\
http_port 3128

acl SSL_ports port 443
acl Safe_ports port 80
acl Safe_ports port 443
acl CONNECT method CONNECT

acl allowed_dst dstdomain {domains}

http_access allow CONNECT SSL_ports allowed_dst
http_access allow allowed_dst
http_access deny CONNECT !SSL_ports
http_access deny all

logformat agent_factory %ts.%03tu %>a %Ss/%03>Hs %rm %ru
access_log stdio:/var/log/squid/access.log agent_factory
cache deny all
"""


def render_squid_conf(allowed_domains: list[str]) -> str:
    """Default-deny egress: only requests to `allowed_domains` (and subdomains) pass."""
    domains = " ".join(f".{d}" if not d.startswith(".") else d for d in allowed_domains)
    return SQUID_CONF_TEMPLATE.format(domains=domains)
