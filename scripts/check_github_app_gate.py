#!/usr/bin/env python3
"""T-203 (SPEC-203): sole owner of GitHub REST API calls is
apps/api/src/api/github_app_client.py — no other tracked *.py file should hardcode
`api.github.com`, mirroring check_llm_router_gate.py's discipline for provider SDKs.

The one disclosed exception: apps/api/tests/test_github_app_client_http.py, which
fault-injects github_app_client.py's real HTTP calls at the HTTP boundary via respx
(T-202's packages/llm_router/tests/test_fallover.py precedent) — it necessarily
references the same URL to mock it.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_FILE = "apps/api/src/api/github_app_client.py"
_ALLOWLISTED_FILES = {
    # respx HTTP-boundary fault injection against github_app_client.py's real calls —
    # necessarily references the same URL to mock it. See that file's own docstring.
    "apps/api/tests/test_github_app_client_http.py",
    # Shared T-203 respx-mock helper (_mock_installation_token), used by both
    # test_repo_router.py and test_github_webhook_router.py — same reason as above.
    "apps/api/tests/integration/conftest.py",
    # Router-level integration tests exercising github_repo_service.py's real calls
    # (connect/provision/export flows) end-to-end via respx — same reason as above.
    "apps/api/tests/integration/test_repo_router.py",
    "apps/api/tests/integration/test_github_webhook_router.py",
    # Pre-existing Squid egress-proxy domain allowlist (SPEC-003) — a literal domain
    # name in a list, not an API call; predates T-203.
    "apps/sandbox/src/sandbox/config.py",
    # T-204: mirrors the same egress domain allowlist above (a literal domain name in a
    # list, not an API call) for the org-scoped effective-domains merge.
    "apps/api/src/api/repositories/egress_repository.py",
    # This gate's own source discusses the pattern it forbids in prose/strings.
    "scripts/check_github_app_gate.py",
}
_URL_RE = re.compile(r"api\.github\.com")


def _tracked_python_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def find_violations() -> list[str]:
    violations = []
    for rel_path in _tracked_python_files():
        if rel_path == ALLOWED_FILE or rel_path in _ALLOWLISTED_FILES:
            continue
        text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _URL_RE.search(line):
                violations.append(f"{rel_path}:{line_no}: {line.strip()}")
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print(
            "github-app gate FAILED - api.github.com referenced outside "
            f"{ALLOWED_FILE}:"
        )
        for v in violations:
            print(f"  {v}")
        return 1

    print(f"github-app gate passed - api.github.com only referenced in {ALLOWED_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
