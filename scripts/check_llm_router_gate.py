#!/usr/bin/env python3
"""T-102 SaaS-readiness rule 2 (docs/00-vision.md): every LLM call goes through
`packages/llm_router` — no provider SDK imported anywhere else. Fails non-zero and
lists offenders if any tracked *.py file outside packages/llm_router imports
anthropic/openai directly.

T-202 (BYOK) closed the claude_runner.py gap this docstring used to describe (real
key injection into the CLI subprocess, see apps/orchestrator/src/orchestrator/
claude_runner.py) — that path never imports a provider SDK, so it was never something
this regex-based gate could or needed to catch.

T-202 also adds ONE narrow, disclosed exception: apps/api/src/api/services/
provider_key_service.py makes a cheap, validate-only provider ping (client.models.
list()-shaped, never a completion call, never touches agent_runs/cost_ledger) to
confirm a newly-added BYOK key is live before it's written to Vault. That's a real,
justified reason for a provider SDK import outside packages/llm_router — see that
file's own docstring and tasks/CHANGELOG.md (T-202) for the full rationale.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_PREFIX = "packages/llm_router/"
_ALLOWLISTED_FILES = {
    # Validate-on-save ping only (T-202) — never a completion call. See module
    # docstring above and provider_key_service.py's own docstring.
    "apps/api/src/api/services/provider_key_service.py",
}
_IMPORT_RE = re.compile(r"^\s*(import|from)\s+(anthropic|openai)\b")


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
        if rel_path.startswith(ALLOWED_PREFIX) or rel_path in _ALLOWLISTED_FILES:
            continue
        text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _IMPORT_RE.match(line):
                violations.append(f"{rel_path}:{line_no}: {line.strip()}")
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print("llm_router gate FAILED - direct provider SDK import(s) found outside "
              f"{ALLOWED_PREFIX}:")
        for v in violations:
            print(f"  {v}")
        return 1

    print(f"llm_router gate passed - no provider SDK imports outside {ALLOWED_PREFIX}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
