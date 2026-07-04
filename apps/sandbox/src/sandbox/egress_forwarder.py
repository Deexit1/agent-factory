import subprocess
import sys
from urllib.parse import urlparse

from sandbox.events_client import post_event


def parse_domain(method: str, url: str) -> str:
    if method == "CONNECT":
        return url.split(":")[0]
    parsed = urlparse(url)
    return parsed.hostname or url


def parse_line(line: str) -> dict[str, object] | None:
    """Parse one line of the `agent_factory` squid access-log format.

    Format: "%ts.%03tu %>a %Ss/%03>Hs %rm %ru" (timestamp, client ip,
    squid-result/http-status, method, url).
    """
    parts = line.split()
    if len(parts) < 5:
        return None
    _ts, client_ip, status_field, method, url = parts[:5]
    squid_result, _, http_code = status_field.partition("/")
    return {
        "egress": parse_domain(method, url),
        "url": url,
        "method": method,
        "http_status": http_code,
        "allowed": "DENIED" not in squid_result,
        "client_ip": client_ip,
    }


def run(ticket_id: str, proxy_container: str, api_url: str) -> None:
    proc = subprocess.Popen(
        ["docker", "exec", proxy_container, "tail", "-F", "-n", "+1", "/var/log/squid/access.log"],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None  # stdout is always a pipe here

    for raw_line in proc.stdout:
        line = raw_line.strip()
        if not line:
            continue
        event = parse_line(line)
        if event is None:
            continue
        try:
            post_event(
                api_url,
                ticket_id,
                actor="system:sandbox-egress-proxy",
                kind="tool_call",
                payload=event,
            )
        except Exception as exc:  # best-effort forwarding; never crash the tail loop
            print(f"egress-forwarder: failed to post event: {exc}", file=sys.stderr)


if __name__ == "__main__":
    _, ticket_id_arg, proxy_container_arg, api_url_arg = sys.argv
    run(ticket_id_arg, proxy_container_arg, api_url_arg)
