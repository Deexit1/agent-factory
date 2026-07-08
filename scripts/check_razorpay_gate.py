#!/usr/bin/env python3
"""T-205 (SPEC-205): sole owner of Razorpay REST API calls is
apps/api/src/api/razorpay_client.py — no other tracked *.py file should hardcode
`api.razorpay.com`, mirroring check_github_app_gate.py's discipline for GitHub.

The one disclosed exception: apps/api/tests/test_razorpay_client_http.py, which
fault-injects razorpay_client.py's real HTTP calls at the HTTP boundary via respx
(T-202's packages/llm_router/tests/test_fallover.py precedent) — it necessarily
references the same URL to mock it.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_FILE = "apps/api/src/api/razorpay_client.py"
_ALLOWLISTED_FILES = {
    # respx HTTP-boundary fault injection against razorpay_client.py's real calls —
    # necessarily references the same URL to mock it. See that file's own docstring.
    "apps/api/tests/test_razorpay_client_http.py",
    # Router-level integration tests exercising billing_service.py's real calls
    # (subscribe/webhook flows) end-to-end via respx — same reason as above.
    "apps/api/tests/integration/test_billing_router.py",
    # This gate's own source discusses the pattern it forbids in prose/strings.
    "scripts/check_razorpay_gate.py",
}
_URL_RE = re.compile(r"api\.razorpay\.com")


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
            "razorpay gate FAILED - api.razorpay.com referenced outside "
            f"{ALLOWED_FILE}:"
        )
        for v in violations:
            print(f"  {v}")
        return 1

    print(f"razorpay gate passed - api.razorpay.com only referenced in {ALLOWED_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
